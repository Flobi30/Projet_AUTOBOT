import sqlite3

import pytest

from autobot.v2.opportunity_scoring import OpportunityConfig, OpportunityScorer
from autobot.v2.pair_strategy_health import (
    PairStrategyHealthConfig,
    PairStrategyHealthEngine,
    load_realized_ledger_trades,
)


pytestmark = pytest.mark.unit


def _create_ledger(path):
    with sqlite3.connect(path) as conn:
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


def test_pair_health_scores_realized_ledger_by_symbol(tmp_path):
    db_path = tmp_path / "state.db"
    _create_ledger(db_path)
    rows = []
    for idx in range(25):
        rows.append(("TRXEUR", "sell", 10.0, 1.0, 0.01, 0.08 if idx < 20 else -0.02, 1, f"2026-05-12T00:{idx:02d}:00+00:00"))
    for idx in range(25):
        rows.append(("XETHZEUR", "sell", 1.0, 100.0, 0.01, -0.08 if idx < 20 else 0.02, 1, f"2026-05-12T01:{idx:02d}:00+00:00"))
    with sqlite3.connect(db_path) as conn:
        conn.executemany("INSERT INTO trade_ledger VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)

    trades = load_realized_ledger_trades(db_path)
    engine = PairStrategyHealthEngine(
        PairStrategyHealthConfig(min_closed_trades=20, lookback_closed_trades=80, max_bonus=8.0, max_penalty=28.0)
    )
    snapshot = engine.build_snapshot(trades, paper_mode=True)

    trx = snapshot["by_symbol"]["TRXEUR"]
    eth = snapshot["by_symbol"]["XETHZEUR"]
    assert trx["health_score"] > 60.0
    assert trx["adjustment"] > 0.0
    assert eth["health_score"] < 50.0
    assert eth["adjustment"] < 0.0
    assert eth["net_pnl_eur"] < 0.0


def test_pair_health_learning_data_does_not_penalize_yet(tmp_path):
    db_path = tmp_path / "state.db"
    _create_ledger(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO trade_ledger VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [("ADAEUR", "sell", 1.0, 1.0, 0.01, -0.1, 1, f"2026-05-12T00:0{i}:00+00:00") for i in range(3)],
        )

    engine = PairStrategyHealthEngine(PairStrategyHealthConfig(min_closed_trades=20))
    snapshot = engine.build_snapshot_from_state_db(db_path, paper_mode=True)

    ada = snapshot["by_symbol"]["ADAEUR"]
    assert ada["status"] == "learning"
    assert ada["adjustment"] == 0.0


def test_opportunity_score_uses_health_without_health_blocker():
    scorer = OpportunityScorer(
        OpportunityConfig(min_score=60.0, min_gross_edge_bps=35.0, min_net_edge_bps=12.0, min_atr_bps=5.0)
    )
    edge_context = {
        "expected_move_bps": 140.0,
        "total_cost_bps": 16.0,
        "net_edge_bps": 124.0,
        "adaptive_min_edge_bps": 18.0,
        "spread_bps": 1.0,
    }

    neutral = scorer.score_signal(
        symbol="XETHZEUR",
        edge_context=edge_context,
        atr_pct=0.002,
        available_capital=500.0,
        paper_mode=True,
    )
    weak = scorer.score_signal(
        symbol="XETHZEUR",
        edge_context=edge_context,
        atr_pct=0.002,
        available_capital=500.0,
        paper_mode=True,
        performance_context={
            "symbol": "XETHZEUR",
            "status": "weak",
            "reason": "realized_health",
            "health_score": 20.0,
            "adjustment": -16.8,
            "closed_trades": 40,
            "net_pnl_eur": -3.0,
            "profit_factor": 0.3,
            "win_rate": 0.2,
            "avg_return_bps": -15.0,
            "max_drawdown_eur": 3.2,
            "enabled": True,
        },
    )

    assert weak.score < neutral.score
    assert weak.health_adjustment < 0.0
    assert weak.health_context["status"] == "weak"
    assert not any(blocker.startswith("health_") for blocker in weak.blockers)
