from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autobot.v2.cli import _build_parser
from autobot.v2.research.alpha_smoke_runner import (
    AlphaSmokeConfig,
    build_alpha_smoke_report,
    write_alpha_smoke_report,
)


pytestmark = pytest.mark.unit


def test_alpha_smoke_runner_is_research_only_and_bounded(tmp_path):
    data_dir = _write_synthetic_ohlcv(tmp_path)
    report = build_alpha_smoke_report(
        AlphaSmokeConfig(
            run_id="pytest_alpha_smoke",
            data_paths=(data_dir,),
            hypotheses_path=Path("docs/research/alpha_hypotheses.json"),
            max_variants=3,
            max_symbols=2,
            max_cpu_seconds=30,
        ),
        commit="test",
    )

    payload = report.to_dict()
    assert payload["paper_capital_allowed"] is False
    assert payload["live_promotion_allowed"] is False
    assert payload["promotable"] is False
    assert {item["hypothesis_id"] for item in payload["tested"]} == {
        "volatility_breakout_high_conviction",
        "long_timeframe_adaptive_trend",
    }
    assert all(item["variant_count"] <= 3 for item in payload["tested"])
    assert all(item["safety"]["paper_capital_allowed"] is False for item in payload["tested"])
    assert all(item["safety"]["live_allowed"] is False for item in payload["tested"])
    assert {item["hypothesis_id"] for item in payload["skipped"]} == {"funding_basis", "liquidation_cascade"}
    assert all(item["status"] == "MISSING_DATA" for item in payload["skipped"])


def test_alpha_smoke_report_writer_outputs_json_and_markdown(tmp_path):
    data_dir = _write_synthetic_ohlcv(tmp_path)
    report = build_alpha_smoke_report(
        AlphaSmokeConfig(
            run_id="pytest_alpha_smoke_write",
            data_paths=(data_dir,),
            hypotheses_path=Path("docs/research/alpha_hypotheses.json"),
            max_variants=2,
            max_symbols=1,
        ),
        commit="test",
    )

    written = write_alpha_smoke_report(report, tmp_path / "reports")

    assert written.json_report_path is not None
    assert written.markdown_report_path is not None
    assert Path(written.json_report_path).exists()
    assert Path(written.markdown_report_path).exists()
    markdown = Path(written.markdown_report_path).read_text(encoding="utf-8")
    assert "No live, no paper capital" in markdown
    assert "volatility_breakout_high_conviction" in markdown


def test_alpha_smoke_cli_command_is_registered():
    parser = _build_parser()
    args = parser.parse_args(
        [
            "alpha-smoke-runner",
            "--run-id",
            "x",
            "--data-paths",
            "data/research/daily/ohlcv",
        ]
    )

    assert args.command == "alpha-smoke-runner"
    assert args.max_variants == 5
    assert args.cost_profile == "research_stress"


def test_alpha_smoke_config_rejects_unbounded_variants(tmp_path):
    with pytest.raises(ValueError, match="max_variants"):
        AlphaSmokeConfig(run_id="x", data_paths=(tmp_path,), max_variants=99)


def _write_synthetic_ohlcv(tmp_path: Path) -> Path:
    data_dir = tmp_path / "ohlcv"
    data_dir.mkdir()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for symbol in ("BTCZEUR", "ETHZEUR"):
        _write_rows(data_dir / f"{symbol}_1h.csv", symbol, "1h", start, 120, timedelta(hours=1))
        _write_rows(data_dir / f"{symbol}_15m.csv", symbol, "15m", start, 120, timedelta(minutes=15))
        _write_rows(data_dir / f"{symbol}_5m.csv", symbol, "5m", start, 240, timedelta(minutes=5))
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
            drift = 1.0 + (0.001 if index > 50 else 0.0001)
            open_price = price
            close = price * drift
            high = max(open_price, close) * 1.003
            low = min(open_price, close) * 0.997
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

