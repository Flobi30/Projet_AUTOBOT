from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autobot.v2.research.alpha_hypothesis_runner import (
    AlphaHypothesisRunnerConfig,
    build_alpha_hypothesis_runner_report,
)
from autobot.v2.research.alpha_hypothesis_scheduler import (
    AlphaResearchMemory,
    AlphaSchedulerConfig,
    ResearchMemoryRecord,
    build_alpha_hypothesis_scheduler_report,
)
from autobot.v2.research.volatility_reversal_research_adapter import (
    ADAPTER_ID,
    VolatilityReversalResearchConfig,
    run_volatility_reversal_research_smoke,
)


pytestmark = pytest.mark.unit


def test_closed_bar_reversal_is_net_of_costs_and_never_promotable(tmp_path: Path) -> None:
    data_dir = _reversal_data(tmp_path)
    result = run_volatility_reversal_research_smoke(
        VolatilityReversalResearchConfig(
            run_id="pytest_reversal",
            data_paths=(data_dir,),
            template=_template(minimum_sample_size=2),
            symbols=("BTCZEUR", "ETHZEUR"),
            max_variants=3,
        )
    )

    assert result.adapter_id == ADAPTER_ID
    assert result.decision == "WALK_FORWARD_AVAILABLE"
    assert result.variant_count == 3
    assert result.metrics.trade_count >= 2
    assert result.paper_capital_allowed is False
    assert result.live_allowed is False
    assert result.promotable is False
    first = result.primary_trades[0]
    costs = first.metadata["cost_components_bps"]
    assert first.opened_at >= first.signal_at
    assert first.net_bps == pytest.approx(first.gross_bps - first.cost_bps)
    assert first.net_pnl_eur < first.gross_pnl_eur
    assert first.cost_bps == pytest.approx(sum(costs.values()))
    assert first.metadata["anti_lookahead"] == (
        "prior_window_excludes_signal_bar; signal_uses_closed_bar; entry_is_next_bar_open"
    )
    assert first.metadata["paper_capital_allowed"] is False
    assert all(row["status"] == "research_only" for row in result.variants)


def test_adapter_returns_data_missing_without_closed_history(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    result = run_volatility_reversal_research_smoke(
        VolatilityReversalResearchConfig(
            run_id="pytest_empty",
            data_paths=(empty,),
            template=_template(),
            symbols=("BTCZEUR", "ETHZEUR"),
        )
    )

    assert result.decision == "DATA_MISSING"
    assert result.metrics.trade_count == 0
    assert result.availability.available is False
    assert result.paper_capital_allowed is False


def test_adapter_bounds_variants_and_has_no_runtime_or_order_imports(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="max_variants"):
        VolatilityReversalResearchConfig(
            run_id="pytest_limit",
            data_paths=(tmp_path,),
            template=_template(),
            symbols=("BTCZEUR",),
            max_variants=4,
        )

    source = Path("src/autobot/v2/research/volatility_reversal_research_adapter.py").read_text(encoding="utf-8")
    for forbidden in ("order_router", "paper_trading", "signal_handler", "kraken_client", "create_order"):
        assert forbidden not in source


def test_alpha_runner_binds_distinct_mean_reversion_hypothesis_to_research_adapter(tmp_path: Path) -> None:
    data_dir = _reversal_data(tmp_path)
    report = build_alpha_hypothesis_runner_report(
        AlphaHypothesisRunnerConfig(
            run_id="pytest_reversal_runner",
            hypothesis_id="mean_reversion_volatility_reversal",
            template_id="volatility_reversal_after_extension",
            mode="smoke",
            data_paths=(data_dir,),
            symbols=("BTCZEUR",),
            max_variants=3,
            max_symbols=1,
        ),
        commit="test",
    )

    gates = {gate.gate: gate for gate in report.gates}
    assert set(gates) == {"DATA_CHECK", "FAST_NET_EDGE_TEST"}
    assert gates["FAST_NET_EDGE_TEST"].metrics["adapter_id"] == ADAPTER_ID
    assert gates["FAST_NET_EDGE_TEST"].artifacts["primary_trades"]
    assert report.paper_capital_allowed is False
    assert report.live_allowed is False
    assert report.promotable is False


def test_scheduler_treats_new_template_as_distinct_from_rejected_legacy_mean_reversion(tmp_path: Path) -> None:
    data_dir = _reversal_data(tmp_path)
    memory_path = tmp_path / "memory.json"
    legacy = ResearchMemoryRecord(
        run_id="legacy_mean_reversion",
        hypothesis_id="mean_reversion",
        alpha_family_id="mean_reversion",
        template_id="legacy_runtime_mean_reversion",
        created_at="2026-01-01T00:00:00+00:00",
        data_snapshot={},
        parameters_tested={},
        variant_count=1,
        symbols_tested=("BTCZEUR",),
        gate_results=(),
        final_status="BENCHMARK_REJECTED",
        rejection_reasons=("legacy_configuration_negative",),
        trial_count_for_family=1,
        trial_count_for_template=1,
        related_rejected_hypotheses=("mean_reversion",),
        do_not_rerun_until=None,
        requires_new_data_before_rerun=True,
    )
    AlphaResearchMemory(memory_path, ()).add_record(legacy).write(memory_path)

    report = build_alpha_hypothesis_scheduler_report(
        AlphaSchedulerConfig(
            run_id="pytest_reversal_scheduler",
            state_db=None,
            data_paths=(data_dir,),
            memory_path=memory_path,
        )
    )

    candidate = {item.template_id: item for item in report.candidates}["volatility_reversal_after_extension"]
    assert candidate.hypothesis_id == "mean_reversion_volatility_reversal"
    assert candidate.adapter_ready is True
    assert candidate.status == "RUNNABLE_SMOKE"
    assert ADAPTER_ID not in {item.adapter_id for item in report.adapter_backlog}


def _template(*, minimum_sample_size: int = 50) -> dict[str, object]:
    return {
        "template_id": "volatility_reversal_after_extension",
        "minimum_sample_size": minimum_sample_size,
        "allowed_parameter_ranges": {
            "zscore_entry": [-2.0, -2.5],
            "mean_target_fraction": [0.5, 0.75],
            "max_hold_hours": [24, 48],
        },
    }


def _reversal_data(tmp_path: Path) -> Path:
    directory = tmp_path / "ohlcv"
    directory.mkdir()
    for symbol in ("BTCZEUR", "ETHZEUR"):
        path = directory / f"{symbol}_1h.csv"
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        rows: list[dict[str, object]] = []
        cursor = start
        for _ in range(5):
            for index in range(24):
                close = 100.0 + (0.08 if index % 2 else -0.08)
                rows.append(_row(cursor, symbol, 100.0, close, 100.2, 99.8))
                cursor += timedelta(hours=1)
            rows.append(_row(cursor, symbol, 100.0, 94.0, 100.1, 93.5))
            cursor += timedelta(hours=1)
            rows.append(_row(cursor, symbol, 94.0, 98.0, 100.0, 93.8))
            cursor += timedelta(hours=1)
            rows.append(_row(cursor, symbol, 100.0, 100.0, 100.2, 99.8))
            cursor += timedelta(hours=1)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["timestamp", "open", "high", "low", "close", "volume", "symbol", "timeframe"])
            writer.writeheader()
            writer.writerows(rows)
    return directory


def _row(timestamp: datetime, symbol: str, open_price: float, close: float, high: float, low: float) -> dict[str, object]:
    return {
        "timestamp": timestamp.isoformat(),
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1000.0,
        "symbol": symbol,
        "timeframe": "1h",
    }
