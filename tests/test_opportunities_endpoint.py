import sqlite3
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from autobot.v2.api import dashboard
from autobot.v2.opportunity_scoring import OpportunityConfig, OpportunityScorer


pytestmark = pytest.mark.integration


def _range_price_history(start: float = 100.0):
    return [{"timestamp": f"2026-04-28T00:{i:02d}:00+00:00", "price": start + (i % 6) * 0.02} for i in range(60)]


class _Orchestrator:
    paper_mode = True

    def get_status(self):
        return {
            "running": True,
            "instance_count": 2,
            "websocket_connected": True,
            "capital": {
                "paper_mode": True,
                "source": "paper",
                "source_status": "ok",
                "total_capital": 1000.0,
            },
        }

    def get_instances_snapshot(self):
        return [
            {
                "id": "inst-eth",
                "name": "Grid ETHEUR",
                "symbol": "ETHEUR",
                "capital": 500.0,
                "open_positions": 0,
                "warmup": {"active": False},
                "blocked_reasons": [],
                "last_signal": {
                    "timestamp": "2026-04-28T01:00:00+00:00",
                    "event": "signal_received",
                    "symbol": "ETHEUR",
                    "side": "buy",
                    "price": 1955.72,
                },
                "last_decision": {
                    "timestamp": "2026-04-28T01:00:01+00:00",
                    "event": "buy_accepted",
                    "reason": "all_guards_passed",
                    "symbol": "ETHEUR",
                    "gross_edge_bps": 140.0,
                    "cost_bps": 46.0,
                    "net_edge_bps": 94.0,
                    "min_edge_bps": 48.5,
                    "atr_pct": 0.002,
                    "edge_context": {
                        "expected_move_bps": 140.0,
                        "total_cost_bps": 46.0,
                        "net_edge_bps": 94.0,
                        "adaptive_min_edge_bps": 48.5,
                        "spread_bps": 1.0,
                    },
                },
                "runtime_events": [
                    {"event": "signal_received", "symbol": "ETHEUR", "side": "buy"},
                    {"event": "buy_accepted", "symbol": "ETHEUR", "side": "buy"},
                ],
                "price_history_tail": _range_price_history(1955.0),
            },
            {
                "id": "inst-btc",
                "name": "Grid BTCEUR",
                "symbol": "BTCEUR",
                "capital": 500.0,
                "open_positions": 0,
                "warmup": {"active": True},
                "blocked_reasons": ["no_price"],
                "last_signal": None,
                "last_decision": None,
                "runtime_events": [],
                "price_history_tail": _range_price_history(66500.0),
            },
        ]


class _LargePaperWalletOrchestrator(_Orchestrator):
    def get_status(self):
        status = super().get_status()
        status["capital"] = {
            "paper_mode": True,
            "source": "paper",
            "source_status": "ok",
            "total_capital": 15_000.0,
            "total_balance": 15_000.0,
            "allocated_capital": 800.0,
            "autobot_trading_capital": 800.0,
            "paper_unallocated_reserve": 14_200.0,
        }
        return status


def test_opportunity_scorer_marks_high_edge_signal_tradable():
    scorer = OpportunityScorer(
        OpportunityConfig(
            min_score=60.0,
            min_gross_edge_bps=35.0,
            min_net_edge_bps=12.0,
            min_atr_bps=18.0,
            min_stability=0.40,
        )
    )

    result = scorer.score_signal(
        symbol="ETHEUR",
        edge_context={
            "expected_move_bps": 140.0,
            "total_cost_bps": 46.0,
            "net_edge_bps": 94.0,
            "adaptive_min_edge_bps": 48.5,
            "spread_bps": 1.0,
        },
        atr_pct=0.002,
        available_capital=500.0,
        recent_events=[
            {"event": "signal_received", "symbol": "ETHEUR", "side": "buy"},
            {"event": "buy_accepted", "symbol": "ETHEUR", "side": "buy"},
        ],
    )

    assert result.status == "tradable"
    assert result.score >= 60.0
    assert result.base_score == result.score
    assert result.regime_context["regime"] == "unknown"
    assert result.recommended_order_eur > 0.0


def test_paper_adaptive_atr_allows_high_net_edge_only_in_paper():
    scorer = OpportunityScorer(
        OpportunityConfig(
            min_score=60.0,
            min_gross_edge_bps=35.0,
            min_net_edge_bps=12.0,
            min_atr_bps=18.0,
            paper_relaxed_min_atr_bps=5.0,
            high_net_edge_bps=80.0,
            atr_mode="adaptive",
            min_stability=0.40,
        )
    )
    edge_context = {
        "expected_move_bps": 140.0,
        "total_cost_bps": 46.0,
        "net_edge_bps": 94.0,
        "adaptive_min_edge_bps": 48.5,
        "spread_bps": 1.0,
    }

    paper_result = scorer.score_signal(
        symbol="ETHEUR",
        edge_context=edge_context,
        atr_pct=0.0008,
        available_capital=500.0,
        paper_mode=True,
    )
    live_result = scorer.score_signal(
        symbol="ETHEUR",
        edge_context=edge_context,
        atr_pct=0.0008,
        available_capital=500.0,
        paper_mode=False,
    )

    assert "atr_below_minimum" not in paper_result.blockers
    assert "atr_below_minimum" in live_result.blockers


def test_paper_allocation_can_train_with_larger_bounded_orders():
    scorer = OpportunityScorer(
        OpportunityConfig(
            min_score=60.0,
            min_gross_edge_bps=35.0,
            min_net_edge_bps=12.0,
            min_atr_bps=18.0,
            min_stability=0.40,
            paper_min_order_eur=7.5,
            paper_max_order_eur=40.0,
            paper_order_capital_pct=18.0,
            paper_max_total_exposure_pct=70.0,
        )
    )
    edge_context = {
        "expected_move_bps": 160.0,
        "total_cost_bps": 30.0,
        "net_edge_bps": 130.0,
        "adaptive_min_edge_bps": 48.5,
        "spread_bps": 1.0,
    }

    result = scorer.score_signal(
        symbol="ETHEUR",
        edge_context=edge_context,
        atr_pct=0.003,
        available_capital=800.0,
        total_capital=800.0,
        paper_mode=True,
    )

    assert result.status == "tradable"
    assert 35.0 <= result.recommended_order_eur <= 40.0


def test_paper_allocation_can_floor_to_min_order_when_score_is_good():
    scorer = OpportunityScorer(
        OpportunityConfig(
            min_score=60.0,
            min_gross_edge_bps=35.0,
            min_net_edge_bps=12.0,
            min_atr_bps=5.0,
            min_stability=0.40,
            paper_min_order_eur=7.5,
            paper_max_order_eur=40.0,
            paper_order_capital_pct=18.0,
            paper_max_total_exposure_pct=70.0,
            paper_allow_min_order_floor=True,
        )
    )

    result = scorer.score_signal(
        symbol="BTCEUR",
        edge_context={
            "expected_move_bps": 140.0,
            "total_cost_bps": 46.0,
            "net_edge_bps": 94.0,
            "adaptive_min_edge_bps": 48.5,
            "spread_bps": 1.0,
        },
        atr_pct=0.001,
        available_capital=37.0,
        total_capital=800.0,
        paper_mode=True,
    )

    assert result.status == "tradable"
    assert result.recommended_order_eur == pytest.approx(7.5)
    assert result.allocation_reason == "paper_min_order_floor"


def test_live_allocation_does_not_floor_to_paper_min_order():
    scorer = OpportunityScorer(
        OpportunityConfig(
            min_score=60.0,
            min_gross_edge_bps=35.0,
            min_net_edge_bps=12.0,
            min_atr_bps=5.0,
            min_stability=0.40,
            min_order_eur=7.5,
            max_order_eur=40.0,
        )
    )

    result = scorer.score_signal(
        symbol="BTCEUR",
        edge_context={
            "expected_move_bps": 140.0,
            "total_cost_bps": 46.0,
            "net_edge_bps": 94.0,
            "adaptive_min_edge_bps": 48.5,
            "spread_bps": 1.0,
        },
        atr_pct=0.001,
        available_capital=37.0,
        total_capital=800.0,
        paper_mode=False,
    )

    assert result.status == "tradable"
    assert result.recommended_order_eur == 0.0
    assert result.allocation_reason == "raw_order_below_min_order"


def test_opportunities_endpoint_returns_ranked_runtime_scores(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    monkeypatch.setenv("SETUP_SHADOW_DB_PATH", str(tmp_path / "setup_shadow_lab.db"))
    monkeypatch.setenv("TREND_SHADOW_DB_PATH", str(tmp_path / "trend_shadow_lab.db"))
    monkeypatch.setenv("MEAN_REVERSION_SHADOW_DB_PATH", str(tmp_path / "mean_reversion_shadow_lab.db"))
    dashboard.app.state.orchestrator = _Orchestrator()
    client = TestClient(dashboard.app)

    response = client.get("/api/opportunities", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "paper"
    assert body["execution_gate"]["selection_applies_to_execution"] is True
    assert body["opportunities"][0]["symbol"] == "ETHEUR"
    assert body["opportunities"][0]["status"] == "tradable"
    assert "base_score" in body["opportunities"][0]
    assert "regime_context" in body["opportunities"][0]
    assert not any(str(blocker).startswith("regime_") for blocker in body["opportunities"][0]["blockers"])
    assert "BTCEUR" in {item["symbol"] for item in body["opportunities"]}
    assert body["setup_optimizer"]["live_promotion_allowed"] is False
    assert body["setup_optimizer"]["summary"]["symbols"] == 2
    assert body["setup_shadow"]["paper_only"] is True
    assert body["trend_shadow"]["paper_only"] is True
    assert body["trend_shadow"]["live_promotion_allowed"] is False
    assert body["mean_reversion_shadow"]["paper_only"] is True
    assert body["strategy_router"]["paper_only"] is True
    assert body["strategy_router"]["live_promotion_allowed"] is False


def test_opportunities_endpoint_uses_autobot_capital_not_paper_wallet(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    monkeypatch.setenv("SETUP_SHADOW_DB_PATH", str(tmp_path / "setup_shadow_lab.db"))
    monkeypatch.setenv("TREND_SHADOW_DB_PATH", str(tmp_path / "trend_shadow_lab.db"))
    monkeypatch.setenv("MEAN_REVERSION_SHADOW_DB_PATH", str(tmp_path / "mean_reversion_shadow_lab.db"))
    dashboard.app.state.orchestrator = _LargePaperWalletOrchestrator()
    client = TestClient(dashboard.app)

    response = client.get("/api/opportunities", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 200
    body = response.json()
    assert body["capital"]["total_capital"] == 800.0
    assert body["opportunities"][0]["allocation_eur"] <= 200.0


def test_regime_endpoint_returns_runtime_pairs(monkeypatch):
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    dashboard.app.state.orchestrator = _Orchestrator()
    client = TestClient(dashboard.app)

    response = client.get("/api/regime", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "paper"
    assert body["config"]["enabled"] is True
    assert {item["symbol"] for item in body["symbols"]} == {"ETHEUR", "BTCEUR"}
    assert all("entropy_norm" in item for item in body["symbols"])


def test_setup_optimizer_endpoint_returns_paper_variants(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    monkeypatch.setenv("SETUP_SHADOW_DB_PATH", str(tmp_path / "setup_shadow_lab.db"))
    dashboard.app.state.orchestrator = _Orchestrator()
    client = TestClient(dashboard.app)

    response = client.get("/api/setup-optimizer", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "paper"
    assert body["live_promotion_allowed"] is False
    assert body["summary"]["symbols"] == 2
    rows = {item["symbol"]: item for item in body["setups"]}
    assert "ETHEUR" in rows
    assert rows["ETHEUR"]["selected_variant"]["name"].startswith("grid_")
    assert rows["ETHEUR"]["execution_policy"]["paper_only"] is True
    assert body["setup_shadow"]["paper_only"] is True


def test_setup_shadow_endpoint_returns_isolated_lab(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    monkeypatch.setenv("SETUP_SHADOW_DB_PATH", str(tmp_path / "setup_shadow_lab.db"))
    dashboard.app.state.orchestrator = _Orchestrator()
    client = TestClient(dashboard.app)

    response = client.get("/api/setup-shadow", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "paper_shadow"
    assert body["paper_only"] is True
    assert body["live_promotion_allowed"] is False
    assert body["writes_official_paper_ledger"] is False


def test_trend_shadow_endpoint_returns_isolated_lab(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    monkeypatch.setenv("TREND_SHADOW_DB_PATH", str(tmp_path / "trend_shadow_lab.db"))
    dashboard.app.state.orchestrator = _Orchestrator()
    client = TestClient(dashboard.app)

    response = client.get("/api/trend-shadow", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "paper_shadow"
    assert body["engine"] == "trend_momentum"
    assert body["paper_only"] is True
    assert body["live_promotion_allowed"] is False
    assert body["writes_official_paper_ledger"] is False


def test_mean_reversion_shadow_endpoint_returns_isolated_lab(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    monkeypatch.setenv("MEAN_REVERSION_SHADOW_DB_PATH", str(tmp_path / "mean_reversion_shadow_lab.db"))
    dashboard.app.state.orchestrator = _Orchestrator()
    client = TestClient(dashboard.app)

    response = client.get("/api/mean-reversion-shadow", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "paper_shadow"
    assert body["engine"] == "mean_reversion"
    assert body["paper_only"] is True
    assert body["live_promotion_allowed"] is False
    assert body["writes_official_paper_ledger"] is False


def test_strategy_router_endpoint_returns_paper_controlled_routes(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    monkeypatch.setenv("SETUP_SHADOW_DB_PATH", str(tmp_path / "setup_shadow_lab.db"))
    monkeypatch.setenv("TREND_SHADOW_DB_PATH", str(tmp_path / "trend_shadow_lab.db"))
    monkeypatch.setenv("MEAN_REVERSION_SHADOW_DB_PATH", str(tmp_path / "mean_reversion_shadow_lab.db"))
    dashboard.app.state.orchestrator = _Orchestrator()
    client = TestClient(dashboard.app)

    response = client.get("/api/strategy-router", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 200
    body = response.json()
    assert body["paper_only"] is True
    assert body["live_promotion_allowed"] is False
    assert body["official_execution_enabled"] is True
    assert body["paper_official_execution_enabled"] is True
    assert body["summary"]["symbols"] == 2
    assert {"dynamic_grid", "trend_momentum", "mean_reversion"} <= set(body["shadow_summaries"].keys())
    assert "live stays blocked" in body["message"]


def test_paper_summary_uses_paper_db_realized_pnl_after_restart(monkeypatch, tmp_path):
    db_path = tmp_path / "paper_trades.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE trades (
                txid TEXT,
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
        conn.execute(
            "INSERT INTO trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("buy-1", "TESTEUR", "buy", 1.0, 100.0, 0.1, "2026-05-07T00:00:00+00:00", "filled", "2026-05-07T00:00:00+00:00"),
        )
        conn.execute(
            "INSERT INTO trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("sell-1", "TESTEUR", "sell", 1.0, 102.0, 0.1, "2026-05-07T00:01:00+00:00", "filled", "2026-05-07T00:01:00+00:00"),
        )

    class _PaperSummaryOrchestrator(_Orchestrator):
        order_executor = SimpleNamespace(db_path=str(db_path))
        persistence = SimpleNamespace(db_path=str(tmp_path / "missing_state.db"))

        def get_instances_snapshot(self):
            return [
                {
                    "id": "inst-test",
                    "symbol": "TESTEUR",
                    "capital": 100.0,
                    "initial_capital": 100.0,
                    "profit": 0.0,
                    "warmup": {"active": False},
                    "blocked_reasons": [],
                    "trades_history": [],
                }
            ]

    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    monkeypatch.setenv("PAPER_TRADING", "true")
    dashboard.app.state.orchestrator = _PaperSummaryOrchestrator()
    client = TestClient(dashboard.app)

    response = client.get("/api/paper-trading/summary", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 200
    pair = response.json()["by_pair"][0]
    assert pair["symbol"] == "TESTEUR"
    assert pair["closed_trades"] == 1
    assert pair["net_pnl_eur"] == pytest.approx(1.8)
    assert pair["avg_pf"] is None
    assert pair["profit_factor_status"] == "no_losses_yet"
    assert pair["win_rate"] == 100.0
    assert pair["pnl_source"] == "paper_trades_db_fifo"
    assert pair["recommendation"] == "continue_paper"


def test_performance_endpoints_use_traceable_trade_ledger(tmp_path, monkeypatch):
    db_path = tmp_path / "autobot_state.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE trade_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id TEXT,
                position_id TEXT,
                instance_id TEXT,
                symbol TEXT,
                side TEXT,
                expected_price REAL,
                executed_price REAL,
                volume REAL,
                fees REAL,
                slippage_bps REAL,
                realized_pnl REAL,
                is_opening_leg INTEGER,
                is_closing_leg INTEGER,
                exchange_order_id TEXT,
                decision_id TEXT,
                signal_id TEXT,
                execution_liquidity TEXT,
                created_at TEXT
            )
            """
        )
        rows = [
            ("t1", "p1", "btc", "XXBTZEUR", "sell", 100.0, 101.0, 1.0, 0.1, 2.0, 1, "2026-05-11T00:00:00+00:00"),
            ("t2", "p2", "btc", "XXBTZEUR", "sell", 100.0, 99.0, 1.0, 0.1, -1.0, 1, "2026-05-11T00:01:00+00:00"),
            ("t3", "p3", "eth", "XETHZEUR", "sell", 100.0, 103.0, 1.0, 0.1, 3.0, 1, "2026-05-11T00:02:00+00:00"),
        ]
        conn.executemany(
            """
            INSERT INTO trade_ledger (
                trade_id, position_id, instance_id, symbol, side, expected_price,
                executed_price, volume, fees, realized_pnl, is_closing_leg, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    class _PerformanceOrchestrator(_Orchestrator):
        paper_mode = True
        persistence = SimpleNamespace(db_path=str(db_path))

        def get_instances_snapshot(self):
            return [
                {"id": "btc", "symbol": "XXBTZEUR", "capital": 400.0, "initial_capital": 400.0, "profit": -99.0, "trades_history": []},
                {"id": "eth", "symbol": "XETHZEUR", "capital": 400.0, "initial_capital": 400.0, "profit": -99.0, "trades_history": []},
            ]

        def get_instances_snapshot_extended(self):
            return self.get_instances_snapshot()

    monkeypatch.setenv("DASHBOARD_API_TOKEN", "tok")
    monkeypatch.setenv("PAPER_TRADING", "true")
    dashboard.app.state.orchestrator = _PerformanceOrchestrator()
    client = TestClient(dashboard.app)
    headers = {"Authorization": "Bearer tok"}

    global_response = client.get("/api/performance/global", headers=headers)
    pairs_response = client.get("/api/performance/by-pair", headers=headers)

    assert global_response.status_code == 200
    global_body = global_response.json()
    assert global_body["profit_total"] == pytest.approx(4.0)
    assert global_body["total_trades"] == 3
    assert global_body["profit_factor"] == pytest.approx(5.0)
    assert global_body["metric_scope"] == "paper_realized_closed_positions"

    assert pairs_response.status_code == 200
    pairs = {item["symbol"]: item for item in pairs_response.json()["pairs"]}
    assert pairs["XXBTZEUR"]["profit_total"] == pytest.approx(1.0)
    assert pairs["XXBTZEUR"]["profit_factor"] == pytest.approx(2.0)
    assert pairs["XETHZEUR"]["profit_total"] == pytest.approx(3.0)
    assert pairs["XETHZEUR"]["profit_factor"] is None
    assert pairs["XETHZEUR"]["profit_factor_status"] == "no_losses_yet"

    legacy_response = client.get("/api/performance", headers=headers)
    assert legacy_response.status_code == 200
    legacy_body = legacy_response.json()
    assert legacy_body["global"]["total_profit"] == pytest.approx(4.0)
    assert legacy_body["global"]["total_trades"] == 3
    assert legacy_body["global"]["pnl_source"] == "trade_ledger"

    trades_response = client.get("/api/trades?limit=2&scope=closed", headers=headers)
    assert trades_response.status_code == 200
    trades_body = trades_response.json()
    assert trades_body["source"] == "trade_ledger"
    assert trades_body["count"] == 3
    assert trades_body["trades"][0]["pnl"] == pytest.approx(3.0)
    assert trades_body["trades"][0]["trade_type"] == "closing_leg"

    monkeypatch.setenv("SETUP_AUDIT_MIN_CLOSED_TRADES", "2")
    audit_response = client.get("/api/performance/setup-audit", headers=headers)
    assert audit_response.status_code == 200
    audit_body = audit_response.json()
    assert audit_body["live_promotion_allowed"] is False
    assert audit_body["global"]["net_pnl_eur"] == pytest.approx(4.0)
    assert audit_body["setup_optimizer"]["live_promotion_allowed"] is False
    setups = {item["symbol"]: item for item in audit_body["setups"]}
    assert setups["XXBTZEUR"]["verdict"] == "paper_review_candidate"
    assert "realized_edge_positive" in setups["XXBTZEUR"]["root_causes"]
    assert setups["XXBTZEUR"]["recommended_variant"]
