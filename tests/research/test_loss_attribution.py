from datetime import datetime, timezone

import pytest

from autobot.v2.research.loss_attribution import (
    analyze_trade_journal,
    analyze_trade_losses,
    render_loss_attribution_report,
    write_loss_attribution_report,
)
from autobot.v2.research.trade_journal import TradeJournal, TradeRecord


pytestmark = pytest.mark.unit


def _trade(
    *,
    net,
    gross,
    symbol="TRXEUR",
    entry_reason="grid_touch",
    exit_reason="take_profit",
    fees=0.1,
    slippage=0.05,
    spread=0.02,
):
    return TradeRecord(
        run_id="pytest_loss_run",
        strategy_id="dynamic_grid",
        symbol=symbol,
        side="long",
        opened_at=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
        closed_at=datetime(2026, 6, 1, 10, 5, tzinfo=timezone.utc),
        quantity=10.0,
        entry_price=1.0,
        exit_price=1.01,
        gross_pnl_eur=gross,
        net_pnl_eur=net,
        fees_eur=fees,
        slippage_eur=slippage,
        spread_cost_eur=spread,
        entry_reason=entry_reason,
        exit_reason=exit_reason,
    )


def test_loss_attribution_tracks_cost_drag_and_cost_flipped_trades():
    result = analyze_trade_losses(
        [
            _trade(gross=0.5, net=0.25),
            _trade(gross=0.1, net=-0.05, exit_reason="cost_stop"),
            _trade(gross=-0.4, net=-0.6, symbol="XLMZEUR", exit_reason="stop_loss"),
        ]
    )

    assert result.trade_count == 3
    assert result.gross_pnl_eur == pytest.approx(0.2)
    assert result.net_pnl_eur == pytest.approx(-0.4)
    assert result.total_cost_eur == pytest.approx(0.51)
    assert result.cost_flipped_trade_count == 1
    assert result.losing_trade_count == 2
    assert result.winning_trade_count == 1
    assert result.by_exit_reason[0].key == "stop_loss"
    assert {bucket.key for bucket in result.by_symbol} == {"TRXEUR", "XLMZEUR"}


def test_loss_attribution_report_writer_round_trips_journal(tmp_path):
    journal_path = tmp_path / "journal.json"
    TradeJournal([_trade(gross=0.5, net=0.25)]).to_json(journal_path)

    result = write_loss_attribution_report(analyze_trade_journal(journal_path), tmp_path / "reports")
    markdown = render_loss_attribution_report(result)

    assert result.json_report_path
    assert result.markdown_report_path
    assert (tmp_path / "reports" / "pytest_loss_run_loss_attribution.json").exists()
    assert "Cost-Flipped Trades" in markdown
    assert "research-only" in markdown
