from datetime import datetime, timezone

import pytest

from autobot.v2.research.trade_journal import TradeJournal, TradeRecord


pytestmark = pytest.mark.unit


def _trade(symbol="TRXEUR", pnl=1.0, minute=1):
    return TradeRecord(
        run_id="run-1",
        strategy_id="grid_core",
        symbol=symbol,
        side="buy",
        opened_at=datetime(2026, 5, 31, 0, 0, tzinfo=timezone.utc),
        closed_at=datetime(2026, 5, 31, 0, minute, tzinfo=timezone.utc),
        quantity=10.0,
        entry_price=1.0,
        exit_price=1.1,
        gross_pnl_eur=pnl + 0.1,
        net_pnl_eur=pnl,
        fees_eur=0.1,
        entry_reason="signal",
        exit_reason="take_profit",
        regime="range",
    )


def test_trade_journal_sorts_filters_and_builds_equity_curve():
    journal = TradeJournal([_trade("XXBTZEUR", pnl=-0.5, minute=2), _trade("TRXEUR", pnl=1.0, minute=1)])

    assert [trade.symbol for trade in journal.records] == ["TRXEUR", "XXBTZEUR"]
    assert len(journal.filter(symbol="TRXEUR")) == 1
    assert journal.equity_curve(100.0)[-1][1] == 100.5


def test_trade_journal_exports_and_loads_json(tmp_path):
    output = tmp_path / "journal.json"
    journal = TradeJournal([_trade()])

    journal.to_json(output)
    loaded = TradeJournal.from_json(output)

    assert len(loaded.records) == 1
    assert loaded.records[0].symbol == "TRXEUR"
    assert loaded.records[0].duration_seconds == 60.0


def test_trade_journal_rejects_invalid_records():
    invalid = TradeRecord(
        run_id="run-1",
        strategy_id="grid_core",
        symbol="TRXEUR",
        side="buy",
        opened_at=datetime(2026, 5, 31, 0, 1, tzinfo=timezone.utc),
        closed_at=datetime(2026, 5, 31, 0, 0, tzinfo=timezone.utc),
        quantity=10.0,
        entry_price=1.0,
        exit_price=1.1,
        gross_pnl_eur=1.0,
        net_pnl_eur=0.9,
    )

    with pytest.raises(ValueError, match="closed_at"):
        TradeJournal([invalid])
