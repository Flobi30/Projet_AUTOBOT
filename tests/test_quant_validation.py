import math
import sqlite3

import pytest
from fastapi.testclient import TestClient

from autobot.v2.api import dashboard
from autobot.v2.quant_validation import (
    BacktestQualityConfig,
    BacktestQualityEngine,
    QuantValidationEngine,
    TradeObservation,
    VolatilityForecastConfig,
    VolatilityForecastEngine,
)


pytestmark = pytest.mark.unit


def _prices_from_returns(start: float, returns_bps: list[float]) -> list[float]:
    prices = [start]
    price = start
    for ret in returns_bps:
        price *= math.exp(ret / 10000.0)
        prices.append(price)
    return prices


def _vol_engine() -> VolatilityForecastEngine:
    return VolatilityForecastEngine(
        VolatilityForecastConfig(
            windows=(8, 16),
            min_samples=8,
            low_bps=8.0,
            high_bps=60.0,
            extreme_bps=120.0,
            garch_floor_bps=2.0,
        )
    )


def test_volatility_forecast_low_on_stable_series():
    result = _vol_engine().analyze_symbol("ETHEUR", [100.0] * 40)

    assert result.state == "low"
    assert result.forecast_vol_bps <= 8.0
    assert result.sample_count >= 8


def test_volatility_forecast_high_on_large_alternating_returns():
    returns = [150.0, -140.0, 130.0, -125.0] * 8
    result = _vol_engine().analyze_symbol("BTCEUR", _prices_from_returns(100.0, returns))

    assert result.state in {"high", "extreme"}
    assert result.forecast_vol_bps >= 60.0


def test_volatility_forecast_unknown_when_history_is_short():
    result = _vol_engine().analyze_symbol("SOLEUR", [100.0, 100.5])

    assert result.state == "unknown"
    assert result.reason == "insufficient_samples"


def test_backtest_quality_fifo_realizes_closed_paper_pnl():
    engine = BacktestQualityEngine(
        BacktestQualityConfig(min_trades=2, pbo_folds=2, trials=3)
    )
    trades = [
        TradeObservation("ETHEUR", "buy", 1.0, 100.0, 0.1, "2026-04-28T00:00:00+00:00"),
        TradeObservation("ETHEUR", "sell", 1.0, 102.0, 0.1, "2026-04-28T01:00:00+00:00"),
        TradeObservation("BTCEUR", "buy", 1.0, 100.0, 0.1, "2026-04-28T02:00:00+00:00"),
        TradeObservation("BTCEUR", "sell", 1.0, 99.0, 0.1, "2026-04-28T03:00:00+00:00"),
    ]

    snapshot = engine.build_snapshot(trades=trades, capital_base=800.0, paper_mode=True)

    assert snapshot["sample"]["executions_count"] == 4
    assert snapshot["sample"]["realized_trade_count"] == 2
    assert snapshot["metrics"]["trade_count"] == 2
    assert snapshot["metrics"]["net_pnl_eur"] == pytest.approx(0.6)
    assert snapshot["by_symbol"][0]["symbol"] == "ETHEUR"


class _Executor:
    db_path = "data/missing-test-paper.db"


class _Persistence:
    db_path = "data/missing-test-state.db"


class _Orchestrator:
    paper_mode = True
    order_executor = _Executor()
    persistence = _Persistence()

    def get_status(self):
        return {
            "running": True,
            "instance_count": 1,
            "websocket_connected": True,
            "capital": {
                "paper_mode": True,
                "source": "paper",
                "source_status": "ok",
                "total_capital": 800.0,
                "autobot_trading_capital": 800.0,
            },
        }

    def get_capital_snapshot(self):
        return self.get_status()["capital"]

    def get_instances_snapshot(self):
        return [
            {
                "id": "inst-eth",
                "name": "Grid ETHEUR",
                "symbol": "ETHEUR",
                "capital": 800.0,
                "price_history_tail": [100.0 + (i % 5) * 0.03 for i in range(50)],
            }
        ]


def test_quant_validation_engine_keeps_live_shadow_policy_visible():
    engine = QuantValidationEngine(volatility=_vol_engine())
    snapshot = engine.build_snapshot(
        instances=_Orchestrator().get_instances_snapshot(),
        trades=[],
        paper_mode=True,
        capital_base=800.0,
    )

    assert snapshot["live_shadow_policy"]["paper_shadow_continues_in_live"] is True
    assert snapshot["live_shadow_policy"]["live_execution_enabled"] is False
    assert snapshot["backtest_quality"]["status"] == "learning"


def test_quant_validation_endpoint_returns_volatility_and_quality(monkeypatch):
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    dashboard.app.state.orchestrator = _Orchestrator()
    client = TestClient(dashboard.app)

    response = client.get("/api/quant/validation", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "paper"
    assert body["runtime"]["running"] is True
    assert body["live_shadow_policy"]["live_execution_enabled"] is False
    assert body["volatility"]["symbols"][0]["symbol"] == "ETHEUR"
    assert body["backtest_quality"]["sample"]["realized_trade_count"] == 0


def test_quant_validation_endpoint_prefers_trade_ledger_when_available(monkeypatch, tmp_path):
    state_db = tmp_path / "state.db"
    paper_db = tmp_path / "paper.db"
    with sqlite3.connect(state_db) as conn:
        conn.execute(
            """
            CREATE TABLE trade_ledger (
                symbol TEXT,
                side TEXT,
                volume REAL,
                executed_price REAL,
                fees REAL,
                realized_pnl REAL,
                is_closing_leg INTEGER,
                created_at TEXT
            )
            """
        )
        conn.executemany(
            "INSERT INTO trade_ledger VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("ETHEUR", "sell", 1.0, 100.0, 0.1, -2.0, 1, "2026-05-12T00:00:00+00:00"),
                ("ETHEUR", "sell", 1.0, 100.0, 0.1, -1.0, 1, "2026-05-12T00:01:00+00:00"),
            ],
        )
    with sqlite3.connect(paper_db) as conn:
        conn.execute(
            """
            CREATE TABLE trades (
                symbol TEXT,
                side TEXT,
                volume REAL,
                price REAL,
                fees REAL,
                timestamp TEXT,
                status TEXT,
                created_at TEXT
            )
            """
        )
        conn.executemany(
            "INSERT INTO trades VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("ETHEUR", "buy", 1.0, 100.0, 0.1, "2026-05-12T00:00:00+00:00", "filled", "2026-05-12T00:00:00+00:00"),
                ("ETHEUR", "sell", 1.0, 120.0, 0.1, "2026-05-12T00:01:00+00:00", "filled", "2026-05-12T00:01:00+00:00"),
            ],
        )

    class _LedgerOrchestrator(_Orchestrator):
        order_executor = type("Executor", (), {"db_path": str(paper_db)})()
        persistence = type("Persistence", (), {"db_path": str(state_db)})()

    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    dashboard.app.state.orchestrator = _LedgerOrchestrator()
    client = TestClient(dashboard.app)

    response = client.get("/api/quant/validation", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 200
    body = response.json()
    assert body["data_sources"]["selected_observation_source"] == "trade_ledger_closing_legs"
    assert body["backtest_quality"]["metrics"]["net_pnl_eur"] == pytest.approx(-3.0)
