from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autobot.v2.research.generic_cross_sectional_ohlcv_adapter import (
    ADAPTER_ID,
    GenericCrossSectionalConfig,
    run_generic_cross_sectional_ohlcv_smoke,
)


pytestmark = pytest.mark.unit


def test_leader_laggard_uses_pre_entry_windows_and_costs(tmp_path):
    data_dir = _write_cross_sectional_ohlcv(tmp_path)
    result = run_generic_cross_sectional_ohlcv_smoke(
        GenericCrossSectionalConfig(
            run_id="pytest_ll",
            mode="leader_laggard_momentum",
            data_paths=(data_dir,),
            template=_template("leader_laggard_momentum"),
            symbols=("LEADEUR", "LAGEUR", "FLATEUR"),
            max_variants=2,
            max_symbols=3,
        )
    )

    assert result.adapter_id == ADAPTER_ID
    assert result.variant_count <= 2
    assert result.metrics.trade_count > 0
    assert result.metrics.total_cost_bps > 0
    trade = next(
        trade
        for variant in result.variants
        for trade in variant["metrics"]["by_symbol"].values()
        if trade["trade_count"] > 0
    )
    assert trade["trade_count"] > 0
    first_trade = _first_trade_from_primary(data_dir, result)
    assert first_trade["signal_at"] < first_trade["opened_at"] < first_trade["closed_at"]
    assert first_trade["metadata"]["anti_lookahead"] == "leader_and_correlation_windows_end_before_entry"
    assert result.paper_capital_allowed is False
    assert result.live_allowed is False
    assert result.promotable is False


def test_relative_strength_respects_max_symbols_and_variants(tmp_path):
    data_dir = _write_cross_sectional_ohlcv(tmp_path)
    result = run_generic_cross_sectional_ohlcv_smoke(
        GenericCrossSectionalConfig(
            run_id="pytest_rs",
            mode="relative_strength_rotation",
            data_paths=(data_dir,),
            template=_template("relative_strength_rotation"),
            symbols=("LEADEUR", "LAGEUR", "FLATEUR"),
            max_variants=1,
            max_symbols=2,
        )
    )

    assert result.mode == "relative_strength_rotation"
    assert result.variant_count == 1
    assert len(result.availability.symbols) == 2
    assert result.metrics.total_cost_bps >= 0
    assert all(row["status"] == "research_only" for row in result.variants)


def test_missing_data_returns_data_missing_without_paper_or_live(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = run_generic_cross_sectional_ohlcv_smoke(
        GenericCrossSectionalConfig(
            run_id="pytest_missing",
            mode="leader_laggard_momentum",
            data_paths=(empty,),
            template=_template("leader_laggard_momentum"),
            symbols=("A", "B"),
            max_variants=1,
            max_symbols=2,
        )
    )

    assert result.decision == "DATA_MISSING"
    assert result.availability.available is False
    assert result.paper_capital_allowed is False
    assert result.live_allowed is False


def _first_trade_from_primary(data_dir: Path, result) -> dict:
    config = GenericCrossSectionalConfig(
        run_id="pytest_ll_replay",
        mode="leader_laggard_momentum",
        data_paths=(data_dir,),
        template=_template("leader_laggard_momentum"),
        symbols=("LEADEUR", "LAGEUR", "FLATEUR"),
        max_variants=1,
        max_symbols=3,
    )
    replay = run_generic_cross_sectional_ohlcv_smoke(config)
    # The public report intentionally does not dump every trade, so this test
    # relies on the deterministic metadata emitted by the first variant summary.
    assert replay.metrics.trade_count == result.metrics.trade_count
    from autobot.v2.research.generic_cross_sectional_ohlcv_adapter import (
        _aligned_rows,
        _group_bars,
        _leader_laggard_trades,
        load_cross_sectional_bars,
    )
    from autobot.v2.research.execution_cost_model import execution_cost_config_for_profile

    bars, _ = load_cross_sectional_bars((data_dir,), max_rows=250_000)
    groups = _group_bars(bars, config.symbols)
    trades = _leader_laggard_trades(
        config,
        groups,
        "1h",
        execution_cost_config_for_profile("research_stress"),
        {"lookback_bars": 24, "min_relative_strength_bps": 120, "min_correlation": 0.2},
    )
    assert trades
    return trades[0].to_dict()


def _template(template_id: str) -> dict:
    if template_id == "leader_laggard_momentum":
        return {
            "template_id": template_id,
            "allowed_parameter_ranges": {
                "lookback_bars": [24, 36],
                "min_relative_strength_bps": [120],
                "min_correlation": [0.2],
            },
        }
    return {
        "template_id": template_id,
        "allowed_parameter_ranges": {
            "rank_lookback_bars": [24, 36],
            "top_n": [1, 2],
            "max_hold_hours": [24],
        },
    }


def _write_cross_sectional_ohlcv(tmp_path: Path) -> Path:
    data_dir = tmp_path / "ohlcv"
    data_dir.mkdir()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _write_symbol(data_dir / "LEADEUR_1h.csv", "LEADEUR", start, drift=1.0020)
    _write_symbol(data_dir / "LAGEUR_1h.csv", "LAGEUR", start, drift=1.0006)
    _write_symbol(data_dir / "FLATEUR_1h.csv", "FLATEUR", start, drift=1.0001)
    return data_dir


def _write_symbol(path: Path, symbol: str, start: datetime, *, drift: float) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["timestamp", "open", "high", "low", "close", "volume", "symbol", "timeframe"],
        )
        writer.writeheader()
        price = 100.0
        for index in range(120):
            pulse = 1.006 if index % 24 in {6, 7, 8} else drift
            open_price = price
            close = price * pulse
            writer.writerow(
                {
                    "timestamp": (start + timedelta(hours=index)).isoformat(),
                    "open": f"{open_price:.8f}",
                    "high": f"{max(open_price, close) * 1.002:.8f}",
                    "low": f"{min(open_price, close) * 0.998:.8f}",
                    "close": f"{close:.8f}",
                    "volume": "1000",
                    "symbol": symbol,
                    "timeframe": "1h",
                }
            )
            price = close
