import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from autobot.v2.paper import shadow_observation_sync
from autobot.v2.paper.ledger_loader import load_state_db_paper_ledger
from autobot.v2.research.daily_data_collection_runner import (
    load_daily_research_data_collection_config,
    run_daily_research_data_collection,
)
from autobot.v2.research.historical_data_collector import KrakenOHLCPage
from autobot.v2.research.trade_journal import TradeRecord


pytestmark = pytest.mark.unit


def _asset_pairs_fixture():
    return {
        "TRXEUR": {"altname": "TRXEUR", "wsname": "TRX/EUR", "base": "TRX", "quote": "ZEUR"},
        "XXBTZEUR": {"altname": "XBTEUR", "wsname": "XBT/EUR", "base": "XXBT", "quote": "ZEUR"},
        "XXRPZEUR": {"altname": "XRPEUR", "wsname": "XRP/EUR", "base": "XXRP", "quote": "ZEUR"},
    }


def _write_config(path, tmp_path):
    path.write_text(
        "\n".join(
            [
                "priority_symbols:",
                "  - TRXEUR",
                "secondary_symbols:",
                "  - BTCZEUR",
                "timeframes:",
                "  - 5m",
                "ohlcv:",
                "  max_pages: 1",
                "  dedupe: true",
                "  fail_on_gaps: false",
                "  export_csv: true",
                "  export_parquet: false",
                "microstructure:",
                "  depth_count: 5",
                "  sample_interval_seconds: 0",
                "  samples_per_run: 1",
                "output_dirs:",
                f"  ohlcv: {str(tmp_path / 'ohlcv').replace(chr(92), '/')}",
                f"  microstructure: {str(tmp_path / 'micro').replace(chr(92), '/')}",
                f"  reports: {str(tmp_path / 'reports').replace(chr(92), '/')}",
                "safety:",
                "  public_endpoints_only: true",
                "  no_private_keys: true",
                "  no_orders: true",
                "  research_only: true",
            ]
        ),
        encoding="utf-8",
    )


def _write_registry(path: Path) -> None:
    payload = {
        "live_auto_promotion_allowed": False,
        "hypotheses": [
            {
                "strategy_id": strategy,
                "family": strategy,
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
                "validation_status": "learning",
                "paper_status": "shadow_only",
                "decision": "continue_testing",
                "decision_reason": "pytest",
            }
            for strategy in ("trend_momentum", "mean_reversion", "high_conviction_swing", "opportunity_scoring")
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _high_conviction_record() -> TradeRecord:
    return TradeRecord(
        run_id="pytest_daily_high_conviction",
        strategy_id="high_conviction_swing",
        symbol="TRXEUR",
        side="buy",
        opened_at=datetime(2026, 6, 7, 0, 0, tzinfo=timezone.utc),
        closed_at=datetime(2026, 6, 7, 1, 0, tzinfo=timezone.utc),
        quantity=100.0,
        entry_price=1.0,
        exit_price=1.1,
        gross_pnl_eur=10.0,
        net_pnl_eur=8.0,
        fees_eur=1.0,
        spread_cost_eur=0.5,
        slippage_eur=0.4,
        latency_cost_eur=0.1,
        entry_reason="pytest",
        exit_reason="fixed_tp",
        regime="trend",
        metadata={"family": "pytest", "policy": "conservative"},
    )


def _epoch_minute(minute: int) -> float:
    return datetime(2026, 6, 7, 0, minute, tzinfo=timezone.utc).timestamp()


def test_daily_runner_collects_public_research_data_and_reports_public_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "secret_key_must_not_leak")
    monkeypatch.setenv("KRAKEN_API_SECRET", "secret_secret_must_not_leak")
    config_path = tmp_path / "research_daily.yaml"
    _write_config(config_path, tmp_path)
    ohlc_calls = []
    depth_calls = []

    def ohlc_fetcher(pair, interval_minutes, since):
        ohlc_calls.append((pair, interval_minutes, since))
        if pair == "XXBTZEUR":
            raise ValueError("public Kraken OHLC error")
        return KrakenOHLCPage(
            pair=pair,
            rows=(
                (_epoch_minute(0), "100", "101", "99", "100.5", "100", "10", 1),
                (_epoch_minute(5), "100.5", "102", "100", "101.0", "101", "11", 2),
            ),
            last=None,
        )

    def depth_fetcher(pair, depth_count):
        depth_calls.append((pair, depth_count))
        if pair == "XXBTZEUR":
            raise ValueError("public Kraken depth error")
        return {
            "error": [],
            "result": {
                pair: {
                    "bids": [["100.0", "2.0", "1780272000"]],
                    "asks": [["100.2", "3.0", "1780272001"]],
                }
            },
        }

    result = run_daily_research_data_collection(
        config_path=config_path,
        run_id="pytest_daily",
        ohlc_fetcher=ohlc_fetcher,
        depth_fetcher=depth_fetcher,
        asset_pairs_fetcher=_asset_pairs_fixture,
    )

    payload = result.to_dict()
    encoded = json.dumps(payload)
    assert result.live_promotion_allowed is False
    assert "secret_key_must_not_leak" not in encoded
    assert "secret_secret_must_not_leak" not in encoded
    assert ohlc_calls == [("TRXEUR", 5, None), ("XXBTZEUR", 5, None)]
    assert depth_calls == [("TRXEUR", 5), ("XXBTZEUR", 5)]
    assert any(op["status"] == "ok" and op["operation_type"] == "ohlcv" for op in payload["operations"])
    assert any(op["status"] == "error" and op["symbol"] == "BTCZEUR" for op in payload["operations"])
    assert any(op["status"] == "partial" and op["operation_type"] == "spread_depth" for op in payload["operations"])
    assert payload["microstructure_result"]["errors"][0]["error"] == "public Kraken depth error"
    assert payload["manifest_path"]
    assert payload["markdown_report_path"]
    assert payload["microstructure_profile_path"]
    assert payload["data_readiness_dashboard_path"]
    canonical_ops = [op for op in payload["operations"] if op["operation_type"] == "canonical_ohlcv"]
    feature_ops = [op for op in payload["operations"] if op["operation_type"] == "canonical_feature_snapshot"]
    assert len(canonical_ops) == 1
    assert canonical_ops[0]["status"] == "ok"
    assert len(feature_ops) == 1
    assert feature_ops[0]["status"] == "ok"
    assert payload["canonical_manifest_path"]
    assert payload["feature_snapshot_manifest_path"]
    assert Path(payload["canonical_manifest_path"]).exists()
    assert Path(payload["feature_snapshot_manifest_path"]).exists()
    assert "No paper or live order is created." in payload["safety_notes"]


def test_daily_runner_rejects_config_that_is_not_research_only(tmp_path):
    config_path = tmp_path / "unsafe.yaml"
    _write_config(config_path, tmp_path)
    text = config_path.read_text(encoding="utf-8").replace("  research_only: true", "  research_only: false")
    config_path.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="safety.research_only must be true"):
        load_daily_research_data_collection_config(config_path)


def test_daily_runner_fails_preflight_for_unknown_active_symbol(tmp_path):
    config_path = tmp_path / "research_daily_unknown.yaml"
    _write_config(config_path, tmp_path)
    text = config_path.read_text(encoding="utf-8").replace("  - BTCZEUR", "  - BADPAIR")
    config_path.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="Kraken public symbol mapping missing"):
        run_daily_research_data_collection(
            config_path=config_path,
            run_id="pytest_daily_unknown",
            asset_pairs_fetcher=_asset_pairs_fixture,
        )


def test_daily_runner_collapses_aliases_to_one_canonical_collection(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADING_PAIRS", "XXRPZEUR")
    config_path = tmp_path / "research_daily_aliases.yaml"
    _write_config(config_path, tmp_path)
    text = (
        config_path.read_text(encoding="utf-8")
        .replace("  - TRXEUR", "  - XRPZEUR")
        .replace("  - BTCZEUR", "  - XRPEUR")
    )
    text = "include_runtime_active_symbols: true\n" + text
    config_path.write_text(text, encoding="utf-8")
    ohlc_calls = []
    depth_calls = []

    def ohlc_fetcher(pair, interval_minutes, since):
        ohlc_calls.append((pair, interval_minutes, since))
        return KrakenOHLCPage(
            pair=pair,
            rows=(
                (_epoch_minute(0), "1.0", "1.1", "0.9", "1.0", "1.0", "10", 1),
                (_epoch_minute(5), "1.0", "1.2", "1.0", "1.1", "1.1", "11", 2),
            ),
            last=None,
        )

    def depth_fetcher(pair, depth_count):
        depth_calls.append((pair, depth_count))
        return {
            "error": [],
            "result": {
                pair: {
                    "bids": [["1.0", "10.0", "1780272000"]],
                    "asks": [["1.1", "10.0", "1780272001"]],
                }
            },
        }

    result = run_daily_research_data_collection(
        config_path=config_path,
        run_id="pytest_daily_alias_collapse",
        ohlc_fetcher=ohlc_fetcher,
        depth_fetcher=depth_fetcher,
        asset_pairs_fetcher=_asset_pairs_fixture,
    )

    assert ohlc_calls == [("XXRPZEUR", 5, None)]
    assert depth_calls == [("XXRPZEUR", 5)]
    ohlcv_ops = [op for op in result.operations if op.operation_type == "ohlcv"]
    assert [op.symbol for op in ohlcv_ops] == ["XRPZEUR"]


def test_daily_runner_writes_research_only_high_conviction_walk_forward_report(tmp_path):
    config_path = tmp_path / "research_daily_high_conviction.yaml"
    _write_config(config_path, tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "\n"
        + "\n".join(
            [
                "high_conviction_walk_forward:",
                "  enabled: true",
                f"  output_dir: {str(tmp_path / 'high_conviction').replace(chr(92), '/')}",
                "  train_window_bars: 5",
                "  test_window_bars: 5",
                "  min_folds: 1",
                "  min_closed_trades_for_review: 50",
                "strategy_orchestrator:",
                "  enabled: true",
                f"  output_dir: {str(tmp_path / 'strategy_orchestrator').replace(chr(92), '/')}",
                "  instance_id: pytest-research-parent",
                "  initial_treasury_eur: 500",
                "  max_open_positions: 3",
                "  signal_history_bars: 24",
                "strategy_edge_review:",
                "  enabled: true",
                f"  output_dir: {str(tmp_path / 'edge').replace(chr(92), '/')}",
            ]
        ),
        encoding="utf-8",
    )

    def ohlc_fetcher(pair, interval_minutes, since):
        return KrakenOHLCPage(
            pair=pair,
            rows=(
                (_epoch_minute(0), "100", "101", "99", "100", "100", "10", 1),
                (_epoch_minute(5), "100", "101", "99", "100", "100", "10", 1),
            ),
            last=None,
        )

    def depth_fetcher(pair, depth_count):
        return {"error": [], "result": {pair: {"bids": [["100", "1", "1"]], "asks": [["101", "1", "1"]]}}}

    result = run_daily_research_data_collection(
        config_path=config_path,
        run_id="pytest_daily_high_conviction",
        ohlc_fetcher=ohlc_fetcher,
        depth_fetcher=depth_fetcher,
        asset_pairs_fetcher=_asset_pairs_fixture,
    )

    high_conviction_ops = [op for op in result.operations if op.operation_type == "high_conviction_walk_forward"]
    assert len(high_conviction_ops) == 1
    assert high_conviction_ops[0].status == "unverified"
    assert "UNVERIFIED_POINT_IN_TIME_RAW_OHLCV" in str(high_conviction_ops[0].error)
    assert result.high_conviction_walk_forward_report_path
    assert Path(result.high_conviction_walk_forward_report_path).exists()
    strategy_orchestrator_ops = [op for op in result.operations if op.operation_type == "strategy_orchestrator"]
    assert len(strategy_orchestrator_ops) == 1
    assert strategy_orchestrator_ops[0].status == "unverified"
    assert "UNVERIFIED_POINT_IN_TIME_RAW_OHLCV" in str(strategy_orchestrator_ops[0].error)
    assert result.strategy_orchestrator_report_path
    assert Path(result.strategy_orchestrator_report_path).exists()
    strategy_edge_ops = [op for op in result.operations if op.operation_type == "strategy_edge_review"]
    assert len(strategy_edge_ops) == 1
    assert strategy_edge_ops[0].status == "skipped"
    assert result.strategy_edge_review_report_path is None
    assert result.live_promotion_allowed is False


def test_daily_runner_blocks_shadow_ledger_sync_without_point_in_time_evidence(tmp_path, monkeypatch):
    config_path = tmp_path / "research_daily_shadow_sync.yaml"
    state_db = tmp_path / "data" / "autobot_state.db"
    registry = tmp_path / "docs" / "research" / "strategy_hypotheses.json"
    state_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(state_db) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS marker (id INTEGER PRIMARY KEY)")
    _write_registry(registry)
    _write_config(config_path, tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "\n"
        + "\n".join(
            [
                "shadow_observation_sync:",
                "  enabled: true",
                f"  state_db_path: {str(state_db).replace(chr(92), '/')}",
                f"  registry_path: {str(registry).replace(chr(92), '/')}",
                f"  trend_shadow_db_path: {str(tmp_path / 'missing_trend.db').replace(chr(92), '/')}",
                f"  mean_reversion_shadow_db_path: {str(tmp_path / 'missing_mean.db').replace(chr(92), '/')}",
                f"  output_dir: {str(tmp_path / 'shadow_reports').replace(chr(92), '/')}",
                f"  high_conviction_output_dir: {str(tmp_path / 'shadow_reports' / 'high_conviction_replay').replace(chr(92), '/')}",
            ]
        ),
        encoding="utf-8",
    )

    def ohlc_fetcher(pair, interval_minutes, since):
        return KrakenOHLCPage(
            pair=pair,
            rows=(
                (_epoch_minute(0), "1.0", "1.1", "1.0", "1.0", "1.0", "10", 1),
                (_epoch_minute(5), "1.0", "1.2", "1.0", "1.1", "1.1", "11", 2),
            ),
            last=None,
        )

    def depth_fetcher(pair, depth_count):
        return {"error": [], "result": {pair: {"bids": [["1.0", "10", "1"]], "asks": [["1.1", "10", "1"]]}}}

    monkeypatch.setattr(
        shadow_observation_sync,
        "build_high_conviction_portfolio_report",
        lambda _config: pytest.fail("daily raw OHLCV must not start a shadow replay without evidence"),
    )

    result = run_daily_research_data_collection(
        config_path=config_path,
        run_id="pytest_daily_shadow_sync",
        ohlc_fetcher=ohlc_fetcher,
        depth_fetcher=depth_fetcher,
        asset_pairs_fetcher=_asset_pairs_fixture,
    )

    shadow_ops = [op for op in result.operations if op.operation_type == "shadow_observation_sync"]
    assert len(shadow_ops) == 1
    assert shadow_ops[0].status == "blocked"
    assert shadow_ops[0].error == "canonical_point_in_time_evidence_required"
    assert result.shadow_observation_sync_report_path is None
    loaded = load_state_db_paper_ledger(state_db)
    assert not loaded.journal.records
