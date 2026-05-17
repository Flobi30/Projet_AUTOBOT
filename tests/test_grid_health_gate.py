import sqlite3
from types import SimpleNamespace

import pytest

from autobot.v2.strategies.grid_async import GridStrategyAsync


pytestmark = pytest.mark.unit


def _state_db(path):
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


def test_grid_blocks_new_buy_when_pair_health_underperforms(tmp_path):
    db_path = tmp_path / "state.db"
    _state_db(db_path)
    rows = []
    for idx in range(24):
        pnl = 0.03 if idx < 13 else -0.04
        rows.append(("XXBTZEUR", "sell", 1.0, 100.0, 0.01, pnl, 1, f"2026-05-12T00:{idx:02d}:00+00:00"))
    with sqlite3.connect(db_path) as conn:
        conn.executemany("INSERT INTO trade_ledger VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)

    instance = SimpleNamespace(
        config=SimpleNamespace(symbol="XXBTZEUR", strategy="grid"),
        orchestrator=SimpleNamespace(paper_mode=True, persistence=SimpleNamespace(db_path=str(db_path))),
        get_available_capital=lambda: 100.0,
        get_current_capital=lambda: 100.0,
        get_profit_factor_days=lambda _days=30: 0.0,
        _trades=[],
    )
    grid = GridStrategyAsync(instance, {"enable_dgt": False})

    blocked, reason = grid._realized_health_blocks_entry()

    assert blocked is True
    assert reason == "pair_health_underperforming"


def test_grid_allows_small_learning_fallback_without_realized_evidence():
    instance = SimpleNamespace(
        config=SimpleNamespace(symbol="NEWEUR", strategy="grid"),
        orchestrator=SimpleNamespace(paper_mode=True, persistence=SimpleNamespace(db_path="missing.db")),
        get_available_capital=lambda: 100.0,
        get_current_capital=lambda: 100.0,
        get_profit_factor_days=lambda _days=30: 0.0,
        _trades=[],
    )
    grid = GridStrategyAsync(instance, {"enable_dgt": False, "kelly_zero_fallback_mult": 0.25})
    grid._runtime_capital_per_level = 20.0
    grid._kelly = SimpleNamespace(calculate_position_size=lambda **_kwargs: 0.0)

    assert grid._calculate_kelly_cpl(10.0) == pytest.approx(5.0)
