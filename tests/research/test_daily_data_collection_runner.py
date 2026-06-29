import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from autobot.v2.research.daily_data_collection_runner import (
    load_daily_research_data_collection_config,
    run_daily_research_data_collection,
)
from autobot.v2.research.historical_data_collector import KrakenOHLCPage


pytestmark = pytest.mark.unit


def _asset_pairs_fixture():
    return {
        "TRXEUR": {"altname": "TRXEUR", "wsname": "TRX/EUR"},
        "XXBTZEUR": {"altname": "XBTEUR", "wsname": "XBT/EUR"},
        "XXRPZEUR": {"altname": "XRPEUR", "wsname": "XRP/EUR"},
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
    assert high_conviction_ops[0].status == "ok"
    assert result.high_conviction_walk_forward_report_path
    assert Path(result.high_conviction_walk_forward_report_path).exists()
    strategy_orchestrator_ops = [op for op in result.operations if op.operation_type == "strategy_orchestrator"]
    assert len(strategy_orchestrator_ops) == 1
    assert strategy_orchestrator_ops[0].status == "ok"
    assert result.strategy_orchestrator_report_path
    assert Path(result.strategy_orchestrator_report_path).exists()
    strategy_edge_ops = [op for op in result.operations if op.operation_type == "strategy_edge_review"]
    assert len(strategy_edge_ops) == 1
    assert strategy_edge_ops[0].status == "ok"
    assert result.strategy_edge_review_report_path
    assert Path(result.strategy_edge_review_report_path).exists()
    assert result.live_promotion_allowed is False
