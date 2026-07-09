from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autobot.v2.cli import _build_parser
from autobot.v2.research.alpha_hypothesis_runner import (
    AlphaHypothesisRunnerConfig,
    build_alpha_hypothesis_runner_report,
    load_alpha_autonomy_policy,
)


pytestmark = pytest.mark.unit


def test_alpha_runner_reads_registry_and_policy_and_stops_missing_data(tmp_path):
    data_dir = _write_ohlcv(tmp_path)
    report = build_alpha_hypothesis_runner_report(
        AlphaHypothesisRunnerConfig(
            run_id="pytest_missing",
            hypothesis_id="funding_basis",
            mode="smoke",
            data_paths=(data_dir,),
            symbols=("BCHEUR", "ADAEUR"),
            max_variants=2,
            max_symbols=2,
        ),
        commit="test",
    )

    payload = report.to_dict()
    assert payload["hypothesis_id"] == "funding_basis"
    assert payload["final_status"] == "DATA_MISSING"
    assert payload["gates"][0]["gate"] == "DATA_CHECK"
    assert payload["gates"][0]["stopped"] is True
    assert all(gate["safety"]["paper_capital_allowed"] is False for gate in payload["gates"])


def test_alpha_runner_smoke_alias_advances_auto_allowed_without_walk_forward(tmp_path):
    data_dir = _write_ohlcv(tmp_path)
    report = build_alpha_hypothesis_runner_report(
        AlphaHypothesisRunnerConfig(
            run_id="pytest_smoke",
            hypothesis_id="volatility_breakout_high_conviction",
            mode="smoke",
            data_paths=(data_dir,),
            symbols=("BCHEUR", "ADAEUR"),
            max_variants=2,
            max_symbols=2,
        ),
        commit="test",
    )

    gates = [gate.to_dict() for gate in report.gates]
    assert report.hypothesis_id == "volatility_breakout"
    assert [gate["gate"] for gate in gates] == ["DATA_CHECK", "FAST_NET_EDGE_TEST"]
    assert all(gate["autonomy_level"] == "AUTO_ALLOWED" for gate in gates)
    assert "WALK_FORWARD" not in {gate["gate"] for gate in gates}
    assert report.paper_capital_allowed is False
    assert report.live_allowed is False
    assert report.promotable is False


def test_alpha_runner_does_not_run_walk_forward_when_fast_test_fails(tmp_path):
    data_dir = _write_ohlcv(tmp_path, falling=True)
    report = build_alpha_hypothesis_runner_report(
        AlphaHypothesisRunnerConfig(
            run_id="pytest_fast_fail",
            hypothesis_id="long_trend",
            mode="walk_forward",
            data_paths=(data_dir,),
            symbols=("BCHEUR", "ADAEUR"),
            max_variants=2,
            max_symbols=2,
        ),
        commit="test",
    )

    gate_names = [gate.gate for gate in report.gates]
    assert "FAST_NET_EDGE_TEST" in gate_names
    assert "WALK_FORWARD" not in gate_names
    assert report.final_status == "REJECT_FAST"


def test_alpha_runner_runs_generic_cross_sectional_smoke_from_template(tmp_path):
    data_dir = _write_ohlcv(tmp_path)
    report = build_alpha_hypothesis_runner_report(
        AlphaHypothesisRunnerConfig(
            run_id="pytest_cross",
            hypothesis_id="cross_momentum",
            mode="smoke",
            data_paths=(data_dir,),
            symbols=("BCHEUR", "ADAEUR"),
            max_variants=2,
            max_symbols=2,
            template_id="leader_laggard_momentum",
        ),
        commit="test",
    )

    gates = {gate.gate: gate for gate in report.gates}
    assert report.hypothesis_id == "cross_momentum"
    assert gates["DATA_CHECK"].passed is True
    assert gates["FAST_NET_EDGE_TEST"].metrics["adapter_id"] == "generic_cross_sectional_ohlcv_adapter"
    assert gates["FAST_NET_EDGE_TEST"].metrics["mode_used"] == "leader_laggard_momentum"
    assert gates["FAST_NET_EDGE_TEST"].metrics["variant_count"] <= 2
    assert report.paper_capital_allowed is False
    assert report.live_allowed is False
    assert report.promotable is False


def test_alpha_runner_policy_requires_human_review_for_shadow_gate():
    policy = load_alpha_autonomy_policy("docs/research/alpha_autonomy_policy.json")
    shadow = next(gate for gate in policy["gates"] if gate["name"] == "SHADOW_REVIEW_CANDIDATE")

    assert shadow["autonomy_level"] == "HUMAN_REVIEW_REQUIRED"
    assert shadow["risk_direction"] == "increase"
    assert shadow["requires_human_approval"] is True


def test_alpha_runner_cli_is_registered():
    parser = _build_parser()
    args = parser.parse_args(
        [
            "alpha-hypothesis-runner",
            "--hypothesis-id",
            "volatility_breakout",
            "--mode",
            "smoke",
            "--state-db",
            "data/autobot_state.db",
            "--data-paths",
            "data/research/daily/ohlcv",
            "--template-id",
            "leader_laggard_momentum",
        ]
    )

    assert args.command == "alpha-hypothesis-runner"
    assert args.max_variants == 5
    assert args.max_symbols == 6
    assert args.template_id == "leader_laggard_momentum"


def test_alpha_runner_rejects_unbounded_variant_count(tmp_path):
    with pytest.raises(ValueError, match="max_variants"):
        AlphaHypothesisRunnerConfig(
            run_id="x",
            hypothesis_id="volatility_breakout",
            mode="smoke",
            data_paths=(tmp_path,),
            max_variants=99,
        )


def _write_ohlcv(tmp_path: Path, *, falling: bool = False) -> Path:
    data_dir = tmp_path / "ohlcv"
    data_dir.mkdir()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for symbol in ("BCHEUR", "ADAEUR"):
        _write_rows(data_dir / f"{symbol}_1h.csv", symbol, "1h", start, 150, timedelta(hours=1), falling=falling)
        _write_rows(data_dir / f"{symbol}_15m.csv", symbol, "15m", start, 600, timedelta(minutes=15), falling=falling)
        _write_rows(data_dir / f"{symbol}_5m.csv", symbol, "5m", start, 1800, timedelta(minutes=5), falling=falling)
    return data_dir


def _write_rows(path: Path, symbol: str, timeframe: str, start: datetime, count: int, step: timedelta, *, falling: bool) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["timestamp", "open", "high", "low", "close", "volume", "symbol", "timeframe"],
        )
        writer.writeheader()
        price = 100.0
        for index in range(count):
            drift = 0.999 if falling else (1.0002 if index < count * 0.4 else 1.003)
            open_price = price
            close = price * drift
            high = max(open_price, close) * 1.004
            low = min(open_price, close) * 0.996
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
