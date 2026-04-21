import autobot.v2.persistence as persistence_mod
from autobot.v2.persistence import StatePersistence


def _reset_thread_local_conn():
    conn = getattr(persistence_mod._local, "conn", None)
    if conn is not None:
        conn.close()
        delattr(persistence_mod._local, "conn")


def _pair_map(report):
    return {row["symbol"]: row for row in report["pairs"]}


def test_pair_attribution_metrics_correctness_known_inputs(tmp_path):
    _reset_thread_local_conn()
    db = tmp_path / "state.db"
    p = StatePersistence(db_path=str(db))

    # BTC: +100, -40 => PF=2.5, trades=2, win_rate=0.5, expectancy=30
    assert p.append_trade_ledger(
        trade_id="t1",
        instance_id="i1",
        symbol="XXBTZEUR",
        side="sell",
        executed_price=100.0,
        volume=1.0,
        fees=1.5,
        realized_pnl=100.0,
        is_closing_leg=True,
    )
    assert p.append_trade_ledger(
        trade_id="t2",
        instance_id="i1",
        symbol="XXBTZEUR",
        side="sell",
        executed_price=90.0,
        volume=1.0,
        fees=1.0,
        realized_pnl=-40.0,
        is_closing_leg=True,
    )
    # ETH: +20 only => PF=999 fallback
    assert p.append_trade_ledger(
        trade_id="t3",
        instance_id="i2",
        symbol="XETHZEUR",
        side="sell",
        executed_price=50.0,
        volume=1.0,
        fees=0.5,
        realized_pnl=20.0,
        is_closing_leg=True,
    )

    report = p.get_pair_attribution_report()
    pairs = _pair_map(report)

    btc = pairs["XXBTZEUR"]
    assert btc["total_trades"] == 2
    assert btc["wins"] == 1
    assert btc["losses"] == 1
    assert round(btc["total_realized_pnl"], 6) == 60.0
    assert round(btc["total_fees"], 6) == 2.5
    assert round(btc["profit_factor"], 6) == 2.5
    assert round(btc["win_rate"], 6) == 0.5
    assert round(btc["expectancy"], 6) == 30.0

    eth = pairs["XETHZEUR"]
    assert eth["total_trades"] == 1
    assert eth["wins"] == 1
    assert eth["losses"] == 0
    assert round(eth["total_realized_pnl"], 6) == 20.0
    assert round(eth["total_fees"], 6) == 0.5
    assert eth["profit_factor"] == 999.0
    assert round(eth["win_rate"], 6) == 1.0
    assert round(eth["expectancy"], 6) == 20.0


def test_pair_attribution_report_schema_validity(tmp_path):
    _reset_thread_local_conn()
    db = tmp_path / "state.db"
    p = StatePersistence(db_path=str(db))
    p.append_trade_ledger(
        trade_id="t1",
        instance_id="i1",
        symbol="XXBTZEUR",
        side="sell",
        executed_price=100.0,
        volume=1.0,
        fees=0.2,
        realized_pnl=5.0,
        is_closing_leg=True,
    )

    report = p.get_pair_attribution_report(window_hours=24, limit=5)
    assert {"generated_at", "window_hours", "pair_count", "totals", "pairs"}.issubset(set(report.keys()))
    assert {"total_trades", "total_realized_pnl", "total_fees"}.issubset(set(report["totals"].keys()))
    assert len(report["pairs"]) == 1

    row = report["pairs"][0]
    required_pair_keys = {
        "symbol",
        "total_trades",
        "wins",
        "losses",
        "total_realized_pnl",
        "total_fees",
        "profit_factor",
        "win_rate",
        "expectancy",
        "recent_trades_24h",
        "last_trade_at",
    }
    assert required_pair_keys.issubset(set(row.keys()))


def test_pair_attribution_sparse_or_absent_data_safe_behavior(tmp_path):
    _reset_thread_local_conn()
    db = tmp_path / "state.db"
    p = StatePersistence(db_path=str(db))

    # No ledger rows
    empty = p.get_pair_attribution_report()
    assert empty["pair_count"] == 0
    assert empty["pairs"] == []
    assert empty["totals"]["total_trades"] == 0

    # Opening leg only should not be counted
    assert p.append_trade_ledger(
        trade_id="open-only",
        instance_id="i1",
        symbol="XXBTZEUR",
        side="buy",
        executed_price=100.0,
        volume=1.0,
        realized_pnl=None,
        is_opening_leg=True,
        is_closing_leg=False,
    )
    still_empty = p.get_pair_attribution_report()
    assert still_empty["pair_count"] == 0
    assert still_empty["pairs"] == []
