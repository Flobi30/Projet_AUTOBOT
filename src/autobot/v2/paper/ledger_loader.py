"""Read-only loaders from AUTOBOT paper SQLite ledgers.

These helpers convert runtime paper persistence into the research
``TradeJournal`` and ``PaperDecisionRecord`` contracts used by the daily paper
reporting engine. They open SQLite databases in read-only mode and never mutate
runtime state.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable as IterableABC
from collections import defaultdict, deque
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from autobot.v2.research.trade_journal import TradeJournal, TradeRecord

from .paper_trading_engine import PaperDecisionRecord


SLIPPAGE_ANOMALY_BPS = 100.0


@dataclass(frozen=True)
class PaperLedgerLoadResult:
    source_type: str
    source_path: str
    journal: TradeJournal
    decisions: tuple[PaperDecisionRecord, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def trade_count(self) -> int:
        return len(self.journal.records)

    @property
    def decision_count(self) -> int:
        return len(self.decisions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "source_path": self.source_path,
            "trade_count": self.trade_count,
            "decision_count": self.decision_count,
            "warnings": list(self.warnings),
        }


def load_state_db_paper_ledger(
    db_path: str | Path,
    *,
    report_date: date | None = None,
    include_decisions: bool = True,
) -> PaperLedgerLoadResult:
    """Load closed official paper trades from ``trade_ledger``.

    The loader pairs closing legs with their opening leg by ``position_id``.
    ``realized_pnl`` on the closing row is treated as official net PnL because
    runtime close logic writes net profit after buy/sell fees.
    """

    path = Path(db_path)
    if not path.exists():
        return PaperLedgerLoadResult(
            source_type="state_db_trade_ledger",
            source_path=str(path),
            journal=TradeJournal(),
            warnings=("state_db_missing",),
        )
    warnings: list[str] = []
    with _connect_readonly(path) as conn:
        if not _table_exists(conn, "trade_ledger"):
            return PaperLedgerLoadResult(
                source_type="state_db_trade_ledger",
                source_path=str(path),
                journal=TradeJournal(),
                warnings=("trade_ledger_missing",),
            )
        trade_rows = _select_all(conn, "trade_ledger", "created_at", "id")
        decision_rows = (
            _select_all(conn, "decision_ledger", "created_at", "id")
            if include_decisions and _table_exists(conn, "decision_ledger")
            else []
        )
        position_rows = _select_all(conn, "positions", "open_time", "id") if _table_exists(conn, "positions") else []

    decisions = tuple(_decision_from_row(row) for row in decision_rows)
    decision_lookup = _decision_lookup(decision_rows)
    positions_by_id = {
        str(row.get("id")): row
        for row in position_rows
        if str(row.get("id") or "")
    }
    opening_by_position: dict[str, Mapping[str, Any]] = {}
    for row in trade_rows:
        if not _truthy(row.get("is_opening_leg")):
            continue
        position_id = str(row.get("position_id") or "")
        if position_id and position_id not in opening_by_position:
            opening_by_position[position_id] = row

    records: list[TradeRecord] = []
    for closing in trade_rows:
        if not _truthy(closing.get("is_closing_leg")):
            continue
        closed_at = _parse_datetime(closing.get("created_at"))
        if report_date is not None and closed_at.date() != report_date:
            continue
        if closing.get("realized_pnl") is None:
            missing_ref = closing.get("position_id") or closing.get("trade_id") or closing.get("id")
            warnings.append(f"realized_pnl_missing:{missing_ref}")
            continue
        position_id = str(closing.get("position_id") or "")
        opening = opening_by_position.get(position_id)
        if opening is None:
            warnings.append(f"opening_leg_missing:{position_id or closing.get('trade_id') or closing.get('id')}")
        record = _trade_record_from_ledger_pair(opening, closing, decision_lookup, positions_by_id.get(position_id))
        if record is not None:
            if (record.metadata.get("slippage") or {}).get("anomaly"):
                warnings.append(f"slippage_bps_anomaly:{position_id or closing.get('trade_id') or closing.get('id')}")
            records.append(record)

    filtered_decisions = tuple(
        decision for decision in decisions if report_date is None or decision.timestamp.date() == report_date
    )
    return PaperLedgerLoadResult(
        source_type="state_db_trade_ledger",
        source_path=str(path),
        journal=TradeJournal(records),
        decisions=filtered_decisions,
        warnings=tuple(warnings),
    )


def load_paper_trades_db_journal(
    db_path: str | Path,
    *,
    report_date: date | None = None,
) -> PaperLedgerLoadResult:
    """Load a FIFO closed-trade journal from legacy ``paper_trades.db`` fills."""

    path = Path(db_path)
    if not path.exists():
        return PaperLedgerLoadResult(
            source_type="paper_trades_db_fifo",
            source_path=str(path),
            journal=TradeJournal(),
            warnings=("paper_trades_db_missing",),
        )
    with _connect_readonly(path) as conn:
        if not _table_exists(conn, "trades"):
            return PaperLedgerLoadResult(
                source_type="paper_trades_db_fifo",
                source_path=str(path),
                journal=TradeJournal(),
                warnings=("trades_table_missing",),
            )
        rows = _select_all(conn, "trades", "timestamp", "created_at")

    records = _fifo_records_from_paper_fills(rows, report_date=report_date)
    return PaperLedgerLoadResult(
        source_type="paper_trades_db_fifo",
        source_path=str(path),
        journal=TradeJournal(records),
    )


def _connect_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _select_all(conn: sqlite3.Connection, table: str, *order_columns: str) -> list[dict[str, Any]]:
    columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    order = [column for column in order_columns if column in columns]
    order_clause = f" ORDER BY {', '.join(order)} ASC" if order else ""
    with closing(conn.execute(f"SELECT * FROM {table}{order_clause}")) as cursor:
        return [dict(row) for row in cursor.fetchall()]


def _decision_lookup(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    lookup: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        for key in ("decision_id", "signal_id", "event_id"):
            value = str(row.get(key) or "")
            if value and value not in lookup:
                lookup[value] = row
    return lookup


def _decision_from_row(row: Mapping[str, Any]) -> PaperDecisionRecord:
    payload = _json_object(row.get("payload_json"))
    event_status = str(row.get("event_status") or "")
    reason = str(row.get("reason") or payload.get("reason") or event_status or "unknown")
    action = _decision_action(row, payload)
    status = _paper_status(event_status, reason)
    blockers = tuple(_iter_strings(payload.get("risk_blockers") or payload.get("blockers")))
    if status == "risk_rejected" and not blockers and reason:
        blockers = (reason,)
    warnings = tuple(_iter_strings(payload.get("risk_warnings") or payload.get("warnings")))
    return PaperDecisionRecord(
        timestamp=_parse_datetime(row.get("created_at")),
        strategy_id=str(row.get("engine") or row.get("strategy") or payload.get("strategy_id") or "unknown"),
        symbol=str(row.get("symbol") or payload.get("symbol") or "UNKNOWN").upper(),
        action=action,
        status=status,
        reason=reason,
        risk_blockers=blockers,
        risk_warnings=warnings,
        metadata={
            "source": "decision_ledger",
            "event_id": row.get("event_id"),
            "decision_id": row.get("decision_id"),
            "signal_id": row.get("signal_id"),
            "event_type": row.get("event_type"),
            "event_status": row.get("event_status"),
            "ledger_source": row.get("source"),
            "payload": payload,
        },
    )


def _trade_record_from_ledger_pair(
    opening: Mapping[str, Any] | None,
    closing: Mapping[str, Any],
    decision_lookup: Mapping[str, Mapping[str, Any]],
    position: Mapping[str, Any] | None = None,
) -> TradeRecord | None:
    exit_price = _safe_float(closing.get("executed_price"))
    quantity = _safe_float(closing.get("volume"))
    if exit_price <= 0.0 or quantity <= 0.0:
        return None
    entry_price = _safe_float(opening.get("executed_price")) if opening else 0.0
    if entry_price <= 0.0:
        entry_price = _safe_float(closing.get("expected_price")) or exit_price
    opened_at = _parse_datetime(opening.get("created_at")) if opening else _parse_datetime(closing.get("created_at"))
    closed_at = _parse_datetime(closing.get("created_at"))
    opening_fees = _safe_float(opening.get("fees")) if opening else 0.0
    closing_fees = _safe_float(closing.get("fees"))
    fees = max(0.0, opening_fees + closing_fees)
    opening_slippage = _slippage_breakdown(opening)
    closing_slippage = _slippage_breakdown(closing)
    slippage = opening_slippage["adverse_eur"] + closing_slippage["adverse_eur"]
    favorable_slippage = opening_slippage["favorable_eur"] + closing_slippage["favorable_eur"]
    net_pnl = _safe_float(closing.get("realized_pnl"))
    if closing.get("realized_pnl") is None:
        net_pnl = ((exit_price - entry_price) * quantity) - fees
    gross_pnl = net_pnl + fees
    open_decision = _linked_decision(opening or {}, decision_lookup)
    close_decision = _linked_decision(closing, decision_lookup)
    strategy_id = _strategy_id(open_decision, close_decision, position)
    return TradeRecord(
        run_id="official_paper_ledger",
        strategy_id=strategy_id,
        symbol=str(closing.get("symbol") or (opening or {}).get("symbol") or "UNKNOWN").upper(),
        side=str((opening or {}).get("side") or "buy").lower(),
        opened_at=opened_at,
        closed_at=closed_at,
        quantity=quantity,
        entry_price=entry_price,
        exit_price=exit_price,
        gross_pnl_eur=gross_pnl,
        net_pnl_eur=net_pnl,
        fees_eur=fees,
        slippage_eur=slippage,
        spread_cost_eur=0.0,
        entry_reason=str((open_decision or {}).get("reason") or "trade_ledger_opening_leg"),
        exit_reason=str((close_decision or {}).get("reason") or "trade_ledger_closing_leg"),
        regime=_regime_from_decisions(open_decision, close_decision),
        metadata={
            "source": "trade_ledger",
            "opening_leg_missing": opening is None,
            "opening_leg": _compact_trade_row(opening),
            "closing_leg": _compact_trade_row(closing),
            "position": _compact_position_row(position),
            "strategy_source": _strategy_source(strategy_id, open_decision, close_decision, position),
            "opening_decision": _compact_decision_row(open_decision),
            "closing_decision": _compact_decision_row(close_decision),
            "slippage": {
                "adverse_eur": slippage,
                "favorable_eur": favorable_slippage,
                "opening": opening_slippage,
                "closing": closing_slippage,
                "anomaly": opening_slippage["anomaly"] or closing_slippage["anomaly"],
            },
        },
    )


def _fifo_records_from_paper_fills(
    rows: Sequence[Mapping[str, Any]],
    *,
    report_date: date | None,
) -> list[TradeRecord]:
    queues: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
    records: list[TradeRecord] = []
    for row in rows:
        if str(row.get("status") or "").lower() not in {"filled", "closed"}:
            continue
        symbol = str(row.get("symbol") or "UNKNOWN").upper()
        side = str(row.get("side") or "").lower()
        quantity = _safe_float(row.get("volume"))
        price = _safe_float(row.get("price"))
        if quantity <= 0.0 or price <= 0.0:
            continue
        fill = dict(row)
        fill["remaining_volume"] = quantity
        if side == "buy":
            queues[symbol].append(fill)
            continue
        if side != "sell":
            continue
        closed_at = _parse_datetime(row.get("timestamp"))
        while fill["remaining_volume"] > 1e-12 and queues[symbol]:
            opening = queues[symbol][0]
            matched_qty = min(float(opening["remaining_volume"]), float(fill["remaining_volume"]))
            if matched_qty <= 0.0:
                queues[symbol].popleft()
                continue
            opened_qty = _safe_float(opening.get("volume"))
            closed_qty = _safe_float(fill.get("volume"))
            buy_fee = _safe_float(opening.get("fees")) * (matched_qty / max(opened_qty, 1e-12))
            sell_fee = _safe_float(fill.get("fees")) * (matched_qty / max(closed_qty, 1e-12))
            fees = buy_fee + sell_fee
            entry_price = _safe_float(opening.get("price"))
            gross = (price - entry_price) * matched_qty
            net = gross - fees
            if report_date is None or closed_at.date() == report_date:
                records.append(
                    TradeRecord(
                        run_id="paper_trades_db_fifo",
                        strategy_id="unknown",
                        symbol=symbol,
                        side="buy",
                        opened_at=_parse_datetime(opening.get("timestamp")),
                        closed_at=closed_at,
                        quantity=matched_qty,
                        entry_price=entry_price,
                        exit_price=price,
                        gross_pnl_eur=gross,
                        net_pnl_eur=net,
                        fees_eur=fees,
                        entry_reason="paper_trades_db_buy_fill",
                        exit_reason="paper_trades_db_sell_fill",
                        metadata={
                            "source": "paper_trades_db_fifo",
                            "opening_txid": opening.get("txid"),
                            "closing_txid": fill.get("txid"),
                            "liquidity": {
                                "opening": opening.get("liquidity"),
                                "closing": fill.get("liquidity"),
                            },
                        },
                    )
                )
            opening["remaining_volume"] = float(opening["remaining_volume"]) - matched_qty
            fill["remaining_volume"] = float(fill["remaining_volume"]) - matched_qty
            if opening["remaining_volume"] <= 1e-12:
                queues[symbol].popleft()
    return records


def _linked_decision(
    row: Mapping[str, Any],
    lookup: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    for key in ("decision_id", "signal_id"):
        value = str(row.get(key) or "")
        if value and value in lookup:
            return lookup[value]
    return None


def _strategy_id(*sources: Mapping[str, Any] | None) -> str:
    for source in sources:
        if not source:
            continue
        value = source.get("strategy_id") or source.get("engine") or source.get("strategy")
        if value:
            return str(value)
        for key in ("payload_json", "metadata"):
            payload = _json_object(source.get(key))
            if payload.get("strategy_id"):
                return str(payload["strategy_id"])
            if payload.get("strategy"):
                return str(payload["strategy"])
    return "unknown"


def _strategy_source(
    strategy_id: str,
    open_decision: Mapping[str, Any] | None,
    close_decision: Mapping[str, Any] | None,
    position: Mapping[str, Any] | None,
) -> str:
    if strategy_id == "unknown":
        return "unknown"
    for label, source in (
        ("opening_decision", open_decision),
        ("closing_decision", close_decision),
        ("position", position),
    ):
        if not source:
            continue
        if source.get("strategy_id") or source.get("engine") or source.get("strategy"):
            return label
        for key in ("payload_json", "metadata"):
            payload = _json_object(source.get(key))
            if payload.get("strategy_id") or payload.get("strategy"):
                return label
    return "unknown"


def _regime_from_decisions(*decisions: Mapping[str, Any] | None) -> str | None:
    for decision in decisions:
        if not decision:
            continue
        payload = _json_object(decision.get("payload_json"))
        value = payload.get("regime") or (payload.get("regime_context") or {}).get("regime")
        if value:
            return str(value)
    return None


def _decision_action(row: Mapping[str, Any], payload: Mapping[str, Any]) -> str:
    for value in (payload.get("action"), payload.get("side"), row.get("event_status"), row.get("event_type")):
        text = str(value or "").lower()
        if "buy" in text:
            return "BUY"
        if "sell" in text:
            return "SELL"
        if "hold" in text:
            return "HOLD"
        if "close" in text:
            return "CLOSE"
    return str(row.get("event_type") or "UNKNOWN").upper()


def _paper_status(event_status: str, reason: str) -> str:
    text = f"{event_status} {reason}".lower()
    if "reject" in text or "block" in text or "denied" in text:
        return "risk_rejected"
    if "accepted" in text or "filled" in text or "approved" in text:
        return "accepted"
    if "signal_received" in text:
        return "signal"
    return event_status or "unknown"


def _json_object(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, (str, bytes)) and raw:
        try:
            payload = json.loads(raw)
            return dict(payload) if isinstance(payload, dict) else {}
        except Exception:
            return {}
    return {}


def _iter_strings(value: Any) -> Iterable[str]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, IterableABC):
        return tuple(str(item) for item in value)
    return (str(value),)


def _compact_trade_row(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    keys = (
        "id",
        "trade_id",
        "position_id",
        "instance_id",
        "symbol",
        "side",
        "executed_price",
        "volume",
        "fees",
        "slippage_bps",
        "realized_pnl",
        "strategy_id",
        "timeframe",
        "signal_source",
        "gross_pnl",
        "net_pnl",
        "regime",
        "decision_id",
        "signal_id",
        "created_at",
    )
    return {key: row.get(key) for key in keys if key in row}


def _compact_decision_row(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    keys = ("event_id", "decision_id", "signal_id", "strategy", "engine", "event_type", "event_status", "reason")
    return {key: row.get(key) for key in keys if key in row}


def _compact_position_row(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    keys = ("id", "instance_id", "symbol", "status", "strategy", "open_time")
    return {key: row.get(key) for key in keys if key in row}


def _slippage_breakdown(row: Mapping[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {
            "signed_bps": 0.0,
            "abs_bps": 0.0,
            "adverse_eur": 0.0,
            "favorable_eur": 0.0,
            "anomaly": False,
        }
    slippage_bps = _safe_float(row.get("slippage_bps"))
    notional = abs(_safe_float(row.get("volume")) * _safe_float(row.get("executed_price")))
    value = (abs(slippage_bps) / 10_000.0) * notional
    return {
        "signed_bps": slippage_bps,
        "abs_bps": abs(slippage_bps),
        "adverse_eur": value if slippage_bps > 0.0 else 0.0,
        "favorable_eur": value if slippage_bps < 0.0 else 0.0,
        "anomaly": abs(slippage_bps) > SLIPPAGE_ANOMALY_BPS,
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if result == result and abs(result) != float("inf") else default


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    try:
        return bool(int(value))
    except (TypeError, ValueError):
        return str(value).strip().lower() in {"true", "yes", "on"}


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value or "").strip()
    if not text:
        return datetime.now(timezone.utc)
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
