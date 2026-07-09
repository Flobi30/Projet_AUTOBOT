from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autobot.v2.cli import _build_parser
from autobot.v2.research.volatility_breakout_walk_forward import (
    VolatilityBreakoutWalkForwardConfig,
    build_volatility_breakout_walk_forward_report,
    write_volatility_breakout_walk_forward_report,
)


pytestmark = pytest.mark.unit


def test_volatility_breakout_walk_forward_is_research_only(tmp_path):
    data_dir = _write_breakout_ohlcv(tmp_path)
    report = build_volatility_breakout_walk_forward_report(
        VolatilityBreakoutWalkForwardConfig(
            run_id="pytest_p18c",
            data_paths=(data_dir,),
            symbols=("BCHEUR", "ADAEUR"),
            max_variants=3,
            folds=3,
        ),
        commit="test",
    )

    payload = report.to_dict()
    assert payload["safety"]["paper_capital_allowed"] is False
    assert payload["safety"]["live_allowed"] is False
    assert payload["safety"]["promotable"] is False
    assert payload["primary_scenario"]["label"] == "fixed_tp_sl__min500bps__rr2__hold72h"
    assert len(payload["scenarios"]) == 3
    assert len(payload["folds"]) == 3
    assert payload["diagnostics"]["anti_lookahead"].startswith("Features are generated")


def test_volatility_breakout_writer_outputs_json_and_markdown(tmp_path):
    data_dir = _write_breakout_ohlcv(tmp_path)
    report = build_volatility_breakout_walk_forward_report(
        VolatilityBreakoutWalkForwardConfig(
            run_id="pytest_p18c_write",
            data_paths=(data_dir,),
            symbols=("BCHEUR",),
            max_variants=2,
            folds=3,
        ),
        commit="test",
    )

    written = write_volatility_breakout_walk_forward_report(report, tmp_path / "reports")

    assert written.json_report_path is not None
    assert written.markdown_report_path is not None
    markdown = Path(written.markdown_report_path).read_text(encoding="utf-8")
    assert "No live, no paper capital" in markdown
    assert "P18C Volatility Breakout Walk-Forward" in markdown


def test_volatility_breakout_cli_command_is_registered():
    parser = _build_parser()
    args = parser.parse_args(
        [
            "volatility-breakout-walk-forward",
            "--run-id",
            "x",
            "--data-paths",
            "data/research/daily/ohlcv",
        ]
    )

    assert args.command == "volatility-breakout-walk-forward"
    assert args.max_variants == 5
    assert args.folds == 5
    assert args.cost_profile == "research_stress"


def test_volatility_breakout_config_rejects_massive_sweep(tmp_path):
    with pytest.raises(ValueError, match="max_variants"):
        VolatilityBreakoutWalkForwardConfig(run_id="x", data_paths=(tmp_path,), max_variants=50)


def _write_breakout_ohlcv(tmp_path: Path) -> Path:
    data_dir = tmp_path / "ohlcv"
    data_dir.mkdir()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for symbol in ("BCHEUR", "ADAEUR"):
        _write_rows(data_dir / f"{symbol}_1h.csv", symbol, "1h", start, 180, timedelta(hours=1))
        _write_rows(data_dir / f"{symbol}_15m.csv", symbol, "15m", start, 720, timedelta(minutes=15))
        _write_rows(data_dir / f"{symbol}_5m.csv", symbol, "5m", start, 2160, timedelta(minutes=5))
    return data_dir


def _write_rows(path: Path, symbol: str, timeframe: str, start: datetime, count: int, step: timedelta) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["timestamp", "open", "high", "low", "close", "volume", "symbol", "timeframe"],
        )
        writer.writeheader()
        price = 100.0
        for index in range(count):
            if index < count * 0.35:
                drift = 1.0002
            elif index < count * 0.70:
                drift = 1.004
            else:
                drift = 0.999
            open_price = price
            close = price * drift
            high = max(open_price, close) * (1.006 if index % 17 == 0 else 1.002)
            low = min(open_price, close) * 0.998
            writer.writerow(
                {
                    "timestamp": (start + index * step).isoformat(),
                    "open": f"{open_price:.8f}",
                    "high": f"{high:.8f}",
                    "low": f"{low:.8f}",
                    "close": f"{close:.8f}",
                    "volume": "1000",
                    "symbol": symbol,
                    "timeframe": timeframe,
                }
            )
            price = close
