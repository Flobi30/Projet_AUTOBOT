import sqlite3

import pytest

from autobot.v2.research.decision_trace_audit import (
    DecisionTraceAuditConfig,
    audit_decision_traces,
    render_decision_trace_audit_report,
    write_decision_trace_audit_report,
)


pytestmark = pytest.mark.unit


def _create_schema(path):
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE decision_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            decision_id TEXT,
            signal_id TEXT,
            instance_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            strategy TEXT,
            engine TEXT,
            event_type TEXT NOT NULL,
            event_status TEXT,
            reason TEXT,
            source TEXT NOT NULL,
            payload_json TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE signal_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            outcome_id TEXT NOT NULL,
            decision_ledger_id INTEGER NOT NULL,
            decision_event_id TEXT,
            decision_id TEXT,
            signal_id TEXT,
            instance_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            strategy TEXT,
            engine TEXT,
            side TEXT,
            original_status TEXT,
            rejection_reason TEXT,
            reference_price REAL NOT NULL,
            evaluation_price REAL NOT NULL,
            gross_return_bps REAL NOT NULL,
            estimated_cost_bps REAL NOT NULL,
            net_return_bps REAL NOT NULL,
            horizon_minutes INTEGER NOT NULL,
            outcome_label TEXT NOT NULL,
            source TEXT NOT NULL,
            payload_json TEXT,
            decision_created_at TEXT NOT NULL,
            evaluated_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE orders (
            client_order_id TEXT PRIMARY KEY,
            exchange_order_id TEXT,
            decision_id TEXT,
            signal_id TEXT,
            instance_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            order_type TEXT NOT NULL,
            requested_qty REAL NOT NULL,
            filled_qty REAL NOT NULL DEFAULT 0,
            avg_fill_price REAL,
            status TEXT NOT NULL,
            userref INTEGER,
            retries INTEGER NOT NULL DEFAULT 0,
            last_error_code TEXT,
            last_error_message TEXT,
            created_at TEXT NOT NULL,
            sent_at TEXT,
            ack_at TEXT,
            terminal_at TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE trade_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id TEXT NOT NULL,
            position_id TEXT,
            instance_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            expected_price REAL,
            executed_price REAL NOT NULL,
            volume REAL NOT NULL,
            fees REAL DEFAULT 0,
            slippage_bps REAL,
            realized_pnl REAL,
            is_opening_leg INTEGER DEFAULT 0,
            is_closing_leg INTEGER DEFAULT 0,
            exchange_order_id TEXT,
            decision_id TEXT,
            signal_id TEXT,
            execution_liquidity TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def _insert_decision(conn, **kwargs):
    payload = {
        "event_id": "evt",
        "decision_id": None,
        "signal_id": None,
        "instance_id": "inst",
        "symbol": "TRXEUR",
        "strategy": "grid",
        "engine": "dynamic_grid",
        "event_type": "signal",
        "event_status": "signal_received",
        "reason": "test",
        "source": "pytest",
        "payload_json": "{}",
        "created_at": "2026-06-02T10:00:00+00:00",
    }
    payload.update(kwargs)
    conn.execute(
        """
        INSERT INTO decision_ledger
        (event_id, decision_id, signal_id, instance_id, symbol, strategy, engine,
         event_type, event_status, reason, source, payload_json, created_at)
        VALUES
        (:event_id, :decision_id, :signal_id, :instance_id, :symbol, :strategy, :engine,
         :event_type, :event_status, :reason, :source, :payload_json, :created_at)
        """,
        payload,
    )


def test_rejected_trace_is_complete_when_signal_decision_and_outcome_are_linked(tmp_path):
    db = tmp_path / "state.db"
    conn = _create_schema(db)
    _insert_decision(
        conn,
        event_id="sig_1_event",
        signal_id="sig_1",
        event_type="signal",
        event_status="signal_received",
        created_at="2026-06-02T10:00:00+00:00",
    )
    _insert_decision(
        conn,
        event_id="dec_1_event",
        decision_id="dec_1",
        signal_id="sig_1",
        event_type="decision",
        event_status="buy_rejected",
        reason="cost_guard",
        created_at="2026-06-02T10:01::00+00:00",
    )
    conn.execute(
        """
        INSERT INTO signal_outcomes
        (outcome_id, decision_ledger_id, decision_event_id, decision_id, signal_id,
         instance_id, symbol, strategy, engine, side, original_status, rejection_reason,
         reference_price, evaluation_price, gross_return_bps, estimated_cost_bps,
         net_return_bps, horizon_minutes, outcome_label, source, payload_json,
         decision_created_at, evaluated_at, created_at)
        VALUES
        ('out_1', 2, 'dec_1_event', 'dec_1', 'sig_1', 'inst', 'TRXEUR',
         'grid', 'dynamic_grid', 'buy', 'buy_rejected', 'cost_guard',
         100.0, 99.5, -50.0, 10.0, -60.0, 15, 'saved_loss', 'pytest', '{}',
         '2026-06-02T10:00:00+00:00', '2026-06-02T10:15:00+00:00',
         '2026-06-02T10:30:00+00:00')
        """
    )
    conn.commit()
    conn.close()

    report = audit_decision_traces(DecisionTraceAuditConfig(state_db_path=str(db), run_id="pytest_trace"))

    assert report.summary.trace_count == 1
    assert report.summary.canonical_complete_count == 1
    assert report.summary.rejected_trace_count == 1
    assert report.summary.rejected_with_outcome_count == 1
    assert report.traces[0].trace_id == "decision_id:dec_1"
    assert report.traces[0].has_signal is True
    assert report.traces[0].has_decision is True
    assert report.traces[0].has_outcome is True
    assert report.traces[0].missing_stages == ()


def test_execution_trace_requires_order_trade_and_pnl(tmp_path):
    db = tmp_path / "state.db"
    conn = _create_schema(db)
    _insert_decision(
        conn,
        event_id="sig_2_event",
        signal_id="sig_2",
        event_type="signal",
        event_status="signal_received",
        created_at="2026-06-02T11:00:00+00:00",
    )
    _insert_decision(
        conn,
        event_id="dec_2_event",
        decision_id="dec_2",
        signal_id="sig_2",
        event_type="decision",
        event_status="buy_accepted",
        reason="all_guards_passed",
        created_at="2026-06-02T10:01:00+00:00",
    )
    conn.execute(
        """
        INSERT INTO orders
        (client_order_id, exchange_order_id, decision_id, signal_id, instance_id,
         symbol, side, order_type, requested_qty, filled_qty, avg_fill_price,
         status, userref, retries, last_error_code, last_error_message,
         created_at, sent_at, ack_at, terminal_at, updated_at)
        VALUES
        ('ord_1', 'tx_1', 'dec_2', 'sig_2', 'inst', 'TRXEUR', 'buy',
         'market', 2.0, 2.0, 100.0, 'FILLED', NULL, 0, NULL, NULL,
         '2026-06-02T10:01:00+00:00', NULL, NULL,
         '2026-06-02T10:01:10+00:00', '2026-06-02T10:30:00+00:00')
        """
    )
    conn.execute(
        """
        INSERT INTO trade_ledger
        (trade_id, position_id, instance_id, symbol, side, expected_price,
         executed_price, volume, fees, slippage_bps, realized_pnl,
         is_opening_leg, is_closing_leg, exchange_order_id, decision_id,
         signal_id, execution_liquidity, created_at)
        VALUES
        ('tr_open', 'pos_1', 'inst', 'TRXEUR', 'buy', 100.0, 100.0, 2.0,
         0.10, 4.0, NULL, 1, 0, 'tx_1', 'dec_2', 'sig_2', 'taker',
         '2026-06-02T10:01:30+00:00')
        """
    )
    conn.execute(
        """
        INSERT INTO trade_ledger
        (trade_id, position_id, instance_id, symbol, side, expected_price,
         executed_price, volume, fees, slippage_bps, realized_pnl,
         is_opening_leg, is_closing_leg, exchange_order_id, decision_id,
         signal_id, execution_liquidity, created_at)
        VALUES
        ('tr_close', 'pos_1', 'inst', 'TRXEUR', 'sell', 101.0, 101.0, 2.0,
         0.10, 4.0, 1.80, 0, 1, 'tx_2', 'dec_2', 'sig_2', 'taker',
         '2026-06-02T10:30:00+00:00')
        """
    )
    conn.commit()
    conn.close()

    report = audit_decision_traces(str(db))

    assert report.summary.trace_count == 1
    assert report.summary.execution_trace_count == 1
    assert report.summary.execution_complete_count == 1
    assert report.summary.total_net_pnl_eur == pytest.approx(1.8)
    assert report.traces[0].canonical_complete is True
    assert report.traces[0].has_pnl is True
    assert report.traces[0].net_pnl_eur == pytest.approx(1.8)


def test_incomplete_and_orphaned_rows_are_reported(tmp_path):
    db = tmp_path / "state.db"
    conn = _create_schema(db)
    _insert_decision(
        conn,
        event_id="sig_3_event",
        signal_id="sig_3",
        event_type="signal",
        event_status="signal_received",
    )
    conn.execute(
        """
        INSERT INTO orders
        (client_order_id, exchange_order_id, decision_id, signal_id, instance_id,
         symbol, side, order_type, requested_qty, filled_qty, avg_fill_price,
         status, userref, retries, last_error_code, last_error_message,
         created_at, sent_at, ack_at, terminal_at, updated_at)
        VALUES
        ('orphan_order', NULL, NULL, NULL, 'inst', 'ETHEUR', 'buy',
         'market', 1.0, 0.0, NULL, 'NEW', NULL, 0, NULL, NULL,
         '2026-06-02T10:00:00+00:00', NULL, NULL, NULL,
         '2026-06-02T10:00:00+00:00')
        """
    )
    conn.commit()
    conn.close()

    report = audit_decision_traces(str(db))
    written = write_decision_trace_audit_report(report, tmp_path / "reports")
    markdown = render_decision_trace_audit_report(written)

    assert report.summary.trace_count == 2
    assert report.summary.signal_without_decision_count == 1
    assert report.summary.orphan_order_count == 1
    assert report.summary.missing_stage_counts["decision"] == 2
    assert written.json_report_path
    assert written.markdown_report_path
    assert "Decision Trace Audit" in markdown
    assert "read-only" in markdown


def test_execution_rows_link_by_exchange_order_and_position_when_decision_ids_are_missing(tmp_path):
    db = tmp_path / "state.db"
    conn = _create_schema(db)
    conn.execute(
        """
        INSERT INTO orders
        (client_order_id, exchange_order_id, decision_id, signal_id, instance_id,
         symbol, side, order_type, requested_qty, filled_qty, avg_fill_price,
         status, userref, retries, last_error_code, last_error_message,
         created_at, sent_at, ack_at, terminal_at, updated_at)
        VALUES
        ('ord_exchange_only', 'tx_open', NULL, NULL, 'inst', 'TRXEUR', 'buy',
         'market', 2.0, 2.0, 100.0, 'FILLED', NULL, 0, NULL, NULL,
         '2026-06-02T10:00:00+00:00', NULL, NULL,
         '2026-06-02T10:00:10+00:00', '2026-06-02T10:00:10+00:00')
        """
    )
    conn.execute(
        """
        INSERT INTO trade_ledger
        (trade_id, position_id, instance_id, symbol, side, expected_price,
         executed_price, volume, fees, slippage_bps, realized_pnl,
         is_opening_leg, is_closing_leg, exchange_order_id, decision_id,
         signal_id, execution_liquidity, created_at)
        VALUES
        ('tr_open_exchange_only', 'pos_exchange_only', 'inst', 'TRXEUR', 'buy',
         100.0, 100.0, 2.0, 0.10, 4.0, NULL, 1, 0, 'tx_open', NULL, NULL,
         'taker', '2026-06-02T10:01:00+00:00')
        """
    )
    conn.execute(
        """
        INSERT INTO trade_ledger
        (trade_id, position_id, instance_id, symbol, side, expected_price,
         executed_price, volume, fees, slippage_bps, realized_pnl,
         is_opening_leg, is_closing_leg, exchange_order_id, decision_id,
         signal_id, execution_liquidity, created_at)
        VALUES
        ('tr_close_exchange_only', 'pos_exchange_only', 'inst', 'TRXEUR', 'sell',
         101.0, 101.0, 2.0, 0.10, 4.0, 1.80, 0, 1, 'tx_close', NULL, NULL,
         'taker', '2026-06-02T10:30:00+00:00')
        """
    )
    conn.commit()
    conn.close()

    report = audit_decision_traces(str(db))

    assert report.summary.trace_count == 1
    assert report.summary.orphan_order_count == 1
    assert report.summary.orphan_trade_count == 2
    assert report.summary.execution_trace_count == 1
    assert report.summary.execution_complete_count == 0
    assert report.traces[0].has_order is True
    assert report.traces[0].has_trade is True
    assert report.traces[0].has_pnl is True
    assert report.traces[0].net_pnl_eur == pytest.approx(1.8)
    assert report.traces[0].missing_stages == ("signal", "decision")


def test_decision_trace_audit_is_public_research_export():
    from autobot.v2 import research

    assert research.DecisionTraceAuditConfig is DecisionTraceAuditConfig
    assert research.audit_decision_traces is audit_decision_traces
