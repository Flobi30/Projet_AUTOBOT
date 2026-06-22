import csv
import math
from datetime import datetime, timedelta, timezone

import pytest

from autobot.v2.research.execution_cost_model import execution_cost_config_for_profile
from autobot.v2.research.market_data_repository import MarketBar
from autobot.v2.research.relative_value_engine import (
    RelativeValueConfig,
    RelativeValueRelation,
    _build_relation_series,
    _discover_signals,
    _group_by_symbol_timeframe,
    _passes_cost_guard,
    build_relative_value_report,
    parse_relationships,
)


pytestmark = pytest.mark.unit


def _bars() -> list[MarketBar]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars: list[MarketBar] = []
    for index in range(180):
        reference = 1.0 + (index * 0.001)
        residual = 0.0005 * math.sin(index / 5.0)
        # Deliberate, temporary target dislocations followed by recovery.
        if index % 36 in {24, 25}:
            residual = -0.040
        target = reference * 1.5 * math.exp(residual)
        timestamp = start + timedelta(minutes=15 * index)
        bars.extend(
            [
                MarketBar(timestamp, target, target * 1.002, target * 0.998, target, 50_000.0, "ADAEUR", "15m"),
                MarketBar(timestamp, reference, reference * 1.002, reference * 0.998, reference, 50_000.0, "XRPZEUR", "15m"),
            ]
        )
    return bars


def _config(tmp_path) -> RelativeValueConfig:
    return RelativeValueConfig(
        run_id="relative_value_pytest",
        data_paths=(tmp_path / "relative_value.csv",),
        relationships=(RelativeValueRelation("ADAEUR", ("XRPZEUR",)),),
        rolling_window_bars=24,
        entry_zscore=-1.0,
        exit_zscore=-0.10,
        min_correlation=0.05,
        min_expected_move_bps=50.0,
        fixed_take_profit_bps=300.0,
        fixed_stop_loss_bps=200.0,
        trailing_activation_bps=150.0,
        trailing_distance_bps=100.0,
        max_hold_bars=12,
        cost_profiles=("paper_current_taker", "research_stress"),
    )


def _write_csv(path, bars: list[MarketBar]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp", "symbol", "timeframe", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        for bar in bars:
            writer.writerow(
                {
                    "timestamp": bar.timestamp.isoformat(),
                    "symbol": bar.symbol,
                    "timeframe": bar.timeframe,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                }
            )


def test_parse_relationships_supports_reference_baskets_and_rejects_self_reference():
    relationships = parse_relationships("ADAEUR:XRPZEUR|DOTEUR,LINKEUR:DOTEUR")

    assert relationships[0].target_symbol == "ADAEUR"
    assert relationships[0].reference_symbols == ("XRPZEUR", "DOTEUR")
    assert relationships[0].relationship_id == "ADAEUR_vs_XRPZEUR_DOTEUR"
    with pytest.raises(ValueError, match="cannot also be a reference"):
        RelativeValueRelation("ADAEUR", ("ADAEUR",))


def test_relative_value_signals_are_target_buy_only(monkeypatch, tmp_path):
    monkeypatch.setattr("autobot.v2.research.relative_value_engine._statsmodels_available", lambda: False)
    config = _config(tmp_path)
    groups = _group_by_symbol_timeframe(_bars())
    series = _build_relation_series(config.relationships[0], groups, "15m")
    assert series is not None

    signals, rejected, statsmodels_available = _discover_signals(config, (series,))

    assert signals
    assert statsmodels_available is False
    assert all(signal.side == "buy" for signal in signals)
    assert all(signal.target_symbol == "ADAEUR" for signal in signals)
    assert all(signal.reference_symbols == ("XRPZEUR",) for signal in signals)
    assert rejected.get("cointegration_pvalue_above_threshold", 0) == 0


def test_cost_guard_rejects_a_move_that_cannot_cover_the_selected_profile(monkeypatch, tmp_path):
    monkeypatch.setattr("autobot.v2.research.relative_value_engine._statsmodels_available", lambda: False)
    config = _config(tmp_path)
    groups = _group_by_symbol_timeframe(_bars())
    series = _build_relation_series(config.relationships[0], groups, "15m")
    assert series is not None
    signal = _discover_signals(config, (series,))[0][0]
    weak_signal = signal.__class__(**{**signal.__dict__, "expected_move_bps": 10.0})

    assert _passes_cost_guard(signal, execution_cost_config_for_profile("research_stress"), config)
    assert not _passes_cost_guard(weak_signal, execution_cost_config_for_profile("research_stress"), config)


def test_cointegration_failure_blocks_signal_when_statsmodels_is_available(monkeypatch, tmp_path):
    monkeypatch.setattr("autobot.v2.research.relative_value_engine._statsmodels_available", lambda: True)
    monkeypatch.setattr("autobot.v2.research.relative_value_engine._cointegration_pvalue", lambda *_args: 0.95)
    config = _config(tmp_path)
    groups = _group_by_symbol_timeframe(_bars())
    series = _build_relation_series(config.relationships[0], groups, "15m")
    assert series is not None

    signals, rejected, _available = _discover_signals(config, (series,))

    assert not signals
    assert rejected["cointegration_pvalue_above_threshold"] > 0


def test_portfolio_report_is_research_only_and_never_trades_reference_symbols(monkeypatch, tmp_path):
    monkeypatch.setattr("autobot.v2.research.relative_value_engine._statsmodels_available", lambda: False)
    data_path = tmp_path / "relative_value.csv"
    _write_csv(data_path, _bars())
    report = build_relative_value_report(_config(tmp_path))

    assert report.live_promotion_allowed is False
    assert report.conclusion.startswith("NO_GO")
    assert all(result.status == "research_only" for result in report.portfolio_results)
    for result in report.portfolio_results:
        assert all(record.side == "buy" for record in result.records)
        assert all(record.symbol == "ADAEUR" for record in result.records)
        assert all(record.metadata["reference_execution"] == "none" for record in result.records)
        assert result.max_open_positions_seen <= 3
