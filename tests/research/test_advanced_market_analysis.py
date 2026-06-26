import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autobot.v2.research.advanced_market_analysis import (
    build_advanced_market_analysis_snapshots,
    preferred_market_context_by_symbol,
)
from autobot.v2.research.market_data_repository import MarketBar


pytestmark = pytest.mark.unit


def _bars(symbol: str = "TRXEUR", timeframe: str = "1h", count: int = 80) -> tuple[MarketBar, ...]:
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    price = 100.0
    rows = []
    for index in range(count):
        price *= 1.0 + (0.004 if index % 7 else -0.001)
        rows.append(
            MarketBar(
                timestamp=start + timedelta(hours=index),
                open=price * 0.998,
                high=price * 1.006,
                low=price * 0.994,
                close=price,
                volume=1000.0,
                symbol=symbol,
                timeframe=timeframe,
            )
        )
    return tuple(rows)


def test_advanced_market_analysis_produces_research_only_standard_signals():
    snapshots = build_advanced_market_analysis_snapshots(
        _bars(),
        microstructure_profiles=(
            {
                "symbol": "TRXEUR",
                "cost_risk_status": "normal",
                "p95_spread_bps": 12.0,
                "median_bid_depth_eur": 5000.0,
                "median_ask_depth_eur": 4800.0,
            },
        ),
        robustness={
            "monte_carlo": {"probability_positive_net_pnl": 0.70, "status": "observation_ready"},
            "stress_scenarios": ({"metrics": {"total_net_pnl_eur": 10.0}},),
        },
        deflated_sharpe={"overfitting_risk_score": 25.0},
    )

    assert len(snapshots) == 1
    snapshot = snapshots[0]
    payload = snapshot.to_dict()
    assert snapshot.research_only is True
    assert snapshot.execution_authority == "none"
    assert payload["paper_candidate_allowed"] is False
    assert payload["live_promotion_allowed"] is False
    assert payload["volatility_regime_signal"] in {
        "low_activity",
        "normal_volatility",
        "volatility_compression",
        "volatility_expansion",
        "high_vol",
    }
    assert payload["trend_regime_signal"] in {"trend_up", "trend_down", "range", "insufficient_data"}
    assert 0.0 <= payload["market_confidence_score"] <= 100.0


def test_preferred_context_selects_one_hour_before_shorter_timeframes():
    snapshots = build_advanced_market_analysis_snapshots(
        (*_bars(timeframe="5m"), *_bars(timeframe="1h")),
    )

    preferred = preferred_market_context_by_symbol(snapshots)

    assert preferred["TRXEUR"].timeframe == "1h"


def test_research_market_modules_do_not_import_runtime_execution_paths():
    root = Path(__file__).resolve().parents[2]
    forbidden = {
        "autobot.v2.paper_trading",
        "autobot.v2.order_executor_async",
        "autobot.v2.order_router",
        "autobot.v2.orchestrator_async",
        "krakenex",
        "sqlite3",
    }
    for relative in (
        "src/autobot/v2/research/advanced_market_analysis.py",
        "src/autobot/v2/research/statistical_validation.py",
        "src/autobot/v2/research/strategy_orchestrator.py",
    ):
        tree = ast.parse((root / relative).read_text(encoding="utf-8"))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        assert imports.isdisjoint(forbidden)
