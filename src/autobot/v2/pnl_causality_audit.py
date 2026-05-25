"""Read-only PnL causality audit for paper trading.

The goal is to explain why official paper trades make or lose money by joining
closing legs, opening legs, and the decision payload captured at entry time.
It intentionally does not tune thresholds or change execution behaviour.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from .pair_strategy_health import symbol_key


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    try:
        value = int(float(raw)) if raw not in (None, "") else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    try:
        value = float(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _round(value: Any, digits: int = 4) -> float:
    return round(_safe_float(value), digits)


def _parse_ts(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _ts(value: Any) -> str | None:
    parsed = _parse_ts(value)
    return parsed.isoformat() if parsed else None


def _read_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, (str, bytes)) or not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _nested(mapping: Mapping[str, Any], *path: str) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _read_only_conn(path: str) -> sqlite3.Connection:
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row["name"])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }


@dataclass(frozen=True)
class PnlCausalityConfig:
    window_hours: int = 720
    limit: int = 1_000
    fee_drag_bps: float = 70.0
    edge_miss_bps: float = 25.0
    tiny_notional_eur: float = 10.0
    weak_profit_factor: float = 0.8
    min_closed_for_action: int = 10

    @classmethod
    def from_env(cls) -> "PnlCausalityConfig":
        return cls(
            window_hours=_env_int("PNL_CAUSALITY_WINDOW_HOURS", 720, 1, 8_760),
            limit=_env_int("PNL_CAUSALITY_LIMIT", 1_000, 1, 50_000),
            fee_drag_bps=_env_float("PNL_CAUSALITY_FEE_DRAG_BPS", 70.0, 0.0, 2_000.0),
            edge_miss_bps=_env_float("PNL_CAUSALITY_EDGE_MISS_BPS", 25.0, 0.0, 5_000.0),
            tiny_notional_eur=_env_float("PNL_CAUSALITY_TINY_NOTIONAL_EUR", 10.0, 0.0, 1_000.0),
            weak_profit_factor=_env_float("PNL_CAUSALITY_WEAK_PF", 0.8, 0.0, 100.0),
            min_closed_for_action=_env_int("PNL_CAUSALITY_MIN_CLOSED_FOR_ACTION", 10, 1, 10_000),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_hours": self.window_hours,
            "limit": self.limit,
            "fee_drag_bps": self.fee_drag_bps,
            "edge_miss_bps": self.edge_miss_bps,
            "tiny_notional_eur": self.tiny_notional_eur,
            "weak_profit_factor": self.weak_profit_factor,
            "min_closed_for_action": self.min_closed_for_action,
        }


class PnlCausalityAuditEngine:
    """Explain realized PnL using the official paper ledger and decision ledger."""

    def __init__(self, config: PnlCausalityConfig | None = None) -> None:
        self.config = config or PnlCausalityConfig.from_env()

    def build_snapshot(self, *, state_db_path: Any, paper_mode: bool) -> dict[str, Any]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.config.window_hours)
        rows, source = self._load_rows(str(state_db_path or ""), cutoff)
        analysed = [self._analyse_row(row) for row in rows]
        summary = self._summary(analysed)

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "paper" if paper_mode else "live_observation",
            "paper_mode": paper_mode,
            "paper_only_analysis": True,
            "live_execution_changed": False,
            "config": self.config.to_dict(),
            "summary": summary,
            "by_symbol": self._grouped(analysed, "symbol"),
            "by_engine": self._grouped(analysed, "entry_engine"),
            "top_loss_trades": sorted(
                analysed,
                key=lambda item: _safe_float(item.get("realized_pnl_eur")),
            )[:25],
            "recent_trades": sorted(
                analysed,
                key=lambda item: str(item.get("closed_at") or ""),
                reverse=True,
            )[:50],
            "data_sources": source,
            "message": (
                "PnL causality joins closing legs with their opening leg and entry decision. "
                "Recommendations are paper governance signals, not live-trading instructions."
            ),
        }

    def _load_rows(self, db_path: str, cutoff: datetime) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        source = {
            "path": db_path,
            "status": "missing",
            "loaded": 0,
            "required_tables": ["trade_ledger"],
            "optional_tables": ["positions", "decision_ledger", "orders"],
        }
        if not db_path or not Path(db_path).exists():
            return [], source

        try:
            with _read_only_conn(db_path) as conn:
                tables = _table_names(conn)
                if "trade_ledger" not in tables:
                    source["status"] = "trade_ledger_missing"
                    return [], source
                has_positions = "positions" in tables
                has_decisions = "decision_ledger" in tables
                has_orders = "orders" in tables
                query = self._query(has_positions=has_positions, has_decisions=has_decisions, has_orders=has_orders)
                rows = [dict(row) for row in conn.execute(query, (cutoff.isoformat(), self.config.limit))]
                source.update(
                    {
                        "status": "ok",
                        "loaded": len(rows),
                        "positions_joined": has_positions,
                        "decision_ledger_joined": has_decisions,
                        "orders_joined": has_orders,
                    }
                )
                return rows, source
        except Exception as exc:
            source.update({"status": "error", "error": str(exc)[:240]})
            return [], source

    @staticmethod
    def _query(*, has_positions: bool, has_decisions: bool, has_orders: bool) -> str:
        position_fields = """
            p.buy_price AS position_entry_price,
            p.strategy AS position_strategy,
            p.open_time AS position_opened_at,
            p.metadata AS position_metadata,
        """ if has_positions else """
            NULL AS position_entry_price,
            NULL AS position_strategy,
            NULL AS position_opened_at,
            NULL AS position_metadata,
        """
        position_join = "LEFT JOIN positions p ON p.id = c.position_id" if has_positions else ""
        decision_fields = """
            d.engine AS entry_decision_engine,
            d.strategy AS entry_decision_strategy,
            d.event_status AS entry_decision_status,
            d.reason AS entry_decision_reason,
            d.payload_json AS entry_decision_payload,
            d.created_at AS entry_decision_created_at,
        """ if has_decisions else """
            NULL AS entry_decision_engine,
            NULL AS entry_decision_strategy,
            NULL AS entry_decision_status,
            NULL AS entry_decision_reason,
            NULL AS entry_decision_payload,
            NULL AS entry_decision_created_at,
        """
        decision_join = """
            LEFT JOIN decision_ledger d
              ON d.decision_id = o.decision_id
             AND d.event_type = 'decision'
        """ if has_decisions else ""
        order_fields = """
            oo.order_type AS entry_order_type,
            oo.status AS entry_order_status,
        """ if has_orders else """
            NULL AS entry_order_type,
            NULL AS entry_order_status,
        """
        order_join = "LEFT JOIN orders oo ON oo.decision_id = o.decision_id" if has_orders else ""
        return f"""
            SELECT
                c.id AS close_id,
                c.trade_id AS close_trade_id,
                c.position_id,
                c.instance_id,
                c.symbol,
                c.side AS close_side,
                c.expected_price AS close_expected_price,
                c.executed_price AS close_executed_price,
                c.volume AS close_volume,
                c.fees AS close_fees,
                c.slippage_bps AS close_slippage_bps,
                c.realized_pnl AS close_realized_pnl,
                c.decision_id AS close_decision_id,
                c.signal_id AS close_signal_id,
                c.execution_liquidity AS close_liquidity,
                c.created_at AS close_created_at,
                o.id AS open_id,
                o.trade_id AS open_trade_id,
                o.expected_price AS open_expected_price,
                o.executed_price AS open_executed_price,
                o.volume AS open_volume,
                o.fees AS open_fees,
                o.slippage_bps AS open_slippage_bps,
                o.decision_id AS open_decision_id,
                o.signal_id AS open_signal_id,
                o.execution_liquidity AS open_liquidity,
                o.created_at AS open_created_at,
                {position_fields}
                {decision_fields}
                {order_fields}
                (
                    SELECT COUNT(*)
                    FROM trade_ledger c2
                    WHERE c2.is_closing_leg = 1
                      AND c2.symbol = c.symbol
                      AND c2.created_at <= c.created_at
                ) AS symbol_close_sequence
            FROM trade_ledger c
            LEFT JOIN trade_ledger o
              ON o.position_id = c.position_id
             AND o.is_opening_leg = 1
            {position_join}
            {decision_join}
            {order_join}
            WHERE c.is_closing_leg = 1
              AND c.created_at >= ?
            ORDER BY c.created_at DESC, c.id DESC
            LIMIT ?
        """

    def _analyse_row(self, row: Mapping[str, Any]) -> dict[str, Any]:
        payload = _read_json(row.get("entry_decision_payload"))
        edge_context = payload.get("edge_context") if isinstance(payload.get("edge_context"), Mapping) else {}
        opportunity = payload.get("opportunity") if isinstance(payload.get("opportunity"), Mapping) else {}
        regime = opportunity.get("regime_context") if isinstance(opportunity.get("regime_context"), Mapping) else {}
        health = opportunity.get("health_context") if isinstance(opportunity.get("health_context"), Mapping) else {}
        atr_context = opportunity.get("atr_context") if isinstance(opportunity.get("atr_context"), Mapping) else {}

        symbol = symbol_key(row.get("symbol"))
        entry_price = _safe_float(row.get("open_executed_price"), _safe_float(row.get("position_entry_price"), 0.0))
        exit_price = _safe_float(row.get("close_executed_price"))
        volume = _safe_float(row.get("close_volume"))
        entry_notional = abs(entry_price * volume)
        exit_notional = abs(exit_price * volume)
        basis_notional = max(entry_notional, exit_notional, 1e-8)
        close_pnl = _safe_float(row.get("close_realized_pnl"))
        open_fees = _safe_float(row.get("open_fees"))
        close_fees = _safe_float(row.get("close_fees"))
        total_fees = open_fees + close_fees
        gross_pnl = close_pnl + total_fees
        gross_return_bps = (gross_pnl / basis_notional) * 10_000.0 if basis_notional > 0.0 else 0.0
        net_return_bps = (close_pnl / basis_notional) * 10_000.0 if basis_notional > 0.0 else 0.0
        fee_bps = (total_fees / basis_notional) * 10_000.0 if basis_notional > 0.0 else 0.0
        slippage_bps = abs(_safe_float(row.get("open_slippage_bps"))) + abs(_safe_float(row.get("close_slippage_bps")))

        expected_gross = _safe_float(
            payload.get("gross_edge_bps"),
            _safe_float(edge_context.get("expected_move_bps"), _safe_float(opportunity.get("gross_edge_bps"))),
        )
        expected_cost = _safe_float(
            payload.get("cost_bps"),
            _safe_float(edge_context.get("total_cost_bps"), _safe_float(opportunity.get("cost_bps"))),
        )
        expected_net = _safe_float(
            payload.get("net_edge_bps"),
            _safe_float(edge_context.get("net_edge_bps"), _safe_float(opportunity.get("net_edge_bps"))),
        )
        min_edge = _safe_float(
            payload.get("min_edge_bps"),
            _safe_float(edge_context.get("adaptive_min_edge_bps"), _safe_float(opportunity.get("min_edge_bps"))),
        )
        expected_available = expected_gross != 0.0 or expected_cost != 0.0 or expected_net != 0.0
        actual_cost_bps = fee_bps + slippage_bps
        edge_capture_bps = net_return_bps - expected_net if expected_available else None

        causes = self._causes(
            row=row,
            close_pnl=close_pnl,
            gross_pnl=gross_pnl,
            gross_return_bps=gross_return_bps,
            net_return_bps=net_return_bps,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
            expected_net=expected_net,
            expected_cost=expected_cost,
            expected_available=expected_available,
            entry_notional=entry_notional,
            regime=regime,
            health=health,
            atr_context=atr_context,
        )
        verdict = self._verdict(close_pnl, causes)

        return {
            "symbol": symbol,
            "position_id": row.get("position_id"),
            "instance_id": row.get("instance_id"),
            "entry_engine": row.get("entry_decision_engine") or row.get("position_strategy") or "unknown",
            "entry_strategy": row.get("entry_decision_strategy") or row.get("position_strategy") or "unknown",
            "entry_order_type": row.get("entry_order_type"),
            "entry_liquidity": row.get("open_liquidity"),
            "exit_liquidity": row.get("close_liquidity"),
            "opened_at": _ts(row.get("open_created_at") or row.get("position_opened_at")),
            "closed_at": _ts(row.get("close_created_at")),
            "hold_minutes": self._hold_minutes(row.get("open_created_at") or row.get("position_opened_at"), row.get("close_created_at")),
            "sequence_for_symbol": _safe_int(row.get("symbol_close_sequence")),
            "entry_price": _round(entry_price, 8),
            "exit_price": _round(exit_price, 8),
            "volume": _round(volume, 8),
            "entry_notional_eur": _round(entry_notional, 4),
            "realized_pnl_eur": _round(close_pnl, 6),
            "gross_pnl_before_fees_eur": _round(gross_pnl, 6),
            "fees_eur": _round(total_fees, 6),
            "fee_bps": round(fee_bps, 2),
            "slippage_bps": round(slippage_bps, 2),
            "actual_cost_bps": round(actual_cost_bps, 2),
            "gross_return_bps": round(gross_return_bps, 2),
            "net_return_bps": round(net_return_bps, 2),
            "expected": {
                "available": expected_available,
                "gross_edge_bps": round(expected_gross, 3) if expected_available else None,
                "cost_bps": round(expected_cost, 3) if expected_available else None,
                "net_edge_bps": round(expected_net, 3) if expected_available else None,
                "min_edge_bps": round(min_edge, 3) if expected_available else None,
                "edge_capture_bps": round(edge_capture_bps, 3) if edge_capture_bps is not None else None,
            },
            "context": {
                "regime": regime.get("regime"),
                "regime_reason": regime.get("reason"),
                "health_status": health.get("status"),
                "health_reason": health.get("reason"),
                "atr_reason": atr_context.get("reason"),
                "entry_decision_status": row.get("entry_decision_status"),
                "entry_decision_reason": row.get("entry_decision_reason"),
            },
            "verdict": verdict,
            "root_causes": causes,
            "recommended_action": self._trade_action(verdict, causes),
        }

    @staticmethod
    def _hold_minutes(opened_at: Any, closed_at: Any) -> float | None:
        opened = _parse_ts(opened_at)
        closed = _parse_ts(closed_at)
        if opened is None or closed is None:
            return None
        return round(max(0.0, (closed - opened).total_seconds() / 60.0), 2)

    def _causes(
        self,
        *,
        row: Mapping[str, Any],
        close_pnl: float,
        gross_pnl: float,
        gross_return_bps: float,
        net_return_bps: float,
        fee_bps: float,
        slippage_bps: float,
        expected_net: float,
        expected_cost: float,
        expected_available: bool,
        entry_notional: float,
        regime: Mapping[str, Any],
        health: Mapping[str, Any],
        atr_context: Mapping[str, Any],
    ) -> list[str]:
        causes: list[str] = []
        if row.get("open_id") is None:
            causes.append("missing_opening_leg")
        if not row.get("entry_decision_payload"):
            causes.append("missing_entry_decision_payload")
        if row.get("position_id") in (None, ""):
            causes.append("missing_position_id")
        if symbol_key(row.get("symbol")) == "UNKNOWN":
            causes.append("unknown_symbol")
        if entry_notional > 0.0 and entry_notional < self.config.tiny_notional_eur:
            causes.append("tiny_notional_fee_sensitive")
        if fee_bps >= self.config.fee_drag_bps:
            causes.append("high_fee_drag")
        if slippage_bps > 10.0:
            causes.append("slippage_drag")
        if expected_available and expected_cost > 0.0 and (fee_bps + slippage_bps) > expected_cost + 10.0:
            causes.append("actual_cost_above_model")
        if expected_available and expected_net > 0.0 and net_return_bps < expected_net - self.config.edge_miss_bps:
            causes.append("expected_edge_not_realized")
        if close_pnl < 0.0 and gross_pnl > 0.0:
            causes.append("fees_erased_positive_move")
        if close_pnl < 0.0 and gross_return_bps < 0.0:
            causes.append("adverse_price_move")
        if str(row.get("open_liquidity") or "").lower() in {"taker", "market", "unknown"}:
            causes.append("entry_not_confirmed_maker")
        if str(row.get("close_liquidity") or "").lower() in {"taker", "market", "unknown"}:
            causes.append("exit_market_or_taker")
        if str(regime.get("regime") or "") in {"low_activity", "chaos"}:
            causes.append(f"regime_{regime.get('regime')}")
        if str(health.get("status") or "") in {"underperforming", "blocked"}:
            causes.append("health_context_underperforming")
        if str(atr_context.get("reason") or "") in {"paper_adaptive_override_allowed", "net_edge_below_adaptive_override"}:
            causes.append("low_atr_context")
        if close_pnl > 0.0 and not causes:
            causes.append("positive_trade_no_issue")
        return sorted(set(causes))

    @staticmethod
    def _verdict(pnl: float, causes: list[str]) -> str:
        if pnl > 0.0:
            return "profitable"
        if "fees_erased_positive_move" in causes:
            return "cost_drag_loss"
        if "expected_edge_not_realized" in causes:
            return "edge_model_miss"
        if "adverse_price_move" in causes:
            return "market_move_loss"
        if pnl < 0.0:
            return "loss_unclassified"
        return "flat"

    @staticmethod
    def _trade_action(verdict: str, causes: list[str]) -> str:
        if verdict == "profitable":
            return "keep_observing"
        if "missing_entry_decision_payload" in causes or "missing_opening_leg" in causes:
            return "fix_traceability_before_tuning"
        if "high_fee_drag" in causes or "fees_erased_positive_move" in causes:
            return "review_execution_costs"
        if "expected_edge_not_realized" in causes:
            return "review_edge_model"
        if "health_context_underperforming" in causes:
            return "keep_in_paper_review"
        return "review_trade_family"

    def _summary(self, rows: list[Mapping[str, Any]]) -> dict[str, Any]:
        return {
            **self._metrics(rows),
            "cause_counts": self._cause_counts(rows),
            "verdict_counts": self._value_counts(rows, "verdict"),
            "action_counts": self._value_counts(rows, "recommended_action"),
            "primary_findings": self._primary_findings(rows),
        }

    def _grouped(self, rows: list[Mapping[str, Any]], key: str) -> list[dict[str, Any]]:
        groups: dict[str, list[Mapping[str, Any]]] = {}
        for row in rows:
            group_key = str(row.get(key) or "unknown")
            groups.setdefault(group_key, []).append(row)
        grouped = []
        for name, group in groups.items():
            metrics = self._metrics(group)
            grouped.append(
                {
                    key: name,
                    **metrics,
                    "cause_counts": self._cause_counts(group, limit=5),
                    "recommended_action": self._group_action(metrics),
                }
            )
        grouped.sort(key=lambda item: (_safe_float(item.get("net_pnl_eur")), _safe_int(item.get("closed_trades"))))
        return grouped

    def _metrics(self, rows: list[Mapping[str, Any]]) -> dict[str, Any]:
        closed = len(rows)
        wins = sum(1 for row in rows if _safe_float(row.get("realized_pnl_eur")) > 0.0)
        losses = sum(1 for row in rows if _safe_float(row.get("realized_pnl_eur")) < 0.0)
        gross_profit = sum(max(0.0, _safe_float(row.get("realized_pnl_eur"))) for row in rows)
        gross_loss = sum(max(0.0, -_safe_float(row.get("realized_pnl_eur"))) for row in rows)
        fees = sum(_safe_float(row.get("fees_eur")) for row in rows)
        gross_before_fees = sum(_safe_float(row.get("gross_pnl_before_fees_eur")) for row in rows)
        net_pnl = gross_profit - gross_loss
        expected_rows = [row for row in rows if _nested(row, "expected", "available")]
        edge_capture_values = [
            _safe_float(_nested(row, "expected", "edge_capture_bps"))
            for row in expected_rows
            if _nested(row, "expected", "edge_capture_bps") is not None
        ]
        return {
            "closed_trades": closed,
            "winning_trades": wins,
            "losing_trades": losses,
            "net_pnl_eur": round(net_pnl, 6),
            "gross_profit_eur": round(gross_profit, 6),
            "gross_loss_eur": round(gross_loss, 6),
            "gross_before_fees_eur": round(gross_before_fees, 6),
            "fees_eur": round(fees, 6),
            "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss > 0.0 else (None if closed == 0 else 999.0),
            "win_rate": round((wins / closed) * 100.0, 2) if closed else 0.0,
            "avg_fee_bps": round(sum(_safe_float(row.get("fee_bps")) for row in rows) / closed, 2) if closed else None,
            "avg_net_return_bps": round(sum(_safe_float(row.get("net_return_bps")) for row in rows) / closed, 2) if closed else None,
            "avg_expected_net_edge_bps": (
                round(sum(_safe_float(_nested(row, "expected", "net_edge_bps")) for row in expected_rows) / len(expected_rows), 2)
                if expected_rows
                else None
            ),
            "avg_edge_capture_bps": (
                round(sum(edge_capture_values) / len(edge_capture_values), 2)
                if edge_capture_values
                else None
            ),
        }

    @staticmethod
    def _value_counts(rows: list[Mapping[str, Any]], key: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in rows:
            value = str(row.get(key) or "unknown")
            counts[value] = counts.get(value, 0) + 1
        return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))

    @staticmethod
    def _cause_counts(rows: list[Mapping[str, Any]], limit: int | None = None) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in rows:
            for cause in row.get("root_causes") or []:
                cause_key = str(cause)
                counts[cause_key] = counts.get(cause_key, 0) + 1
        items = sorted(counts.items(), key=lambda item: item[1], reverse=True)
        if limit is not None:
            items = items[:limit]
        return dict(items)

    def _group_action(self, metrics: Mapping[str, Any]) -> str:
        closed = _safe_int(metrics.get("closed_trades"))
        pnl = _safe_float(metrics.get("net_pnl_eur"))
        pf = metrics.get("profit_factor")
        pf_value = _safe_float(pf, 0.0) if pf is not None else 0.0
        if closed >= self.config.min_closed_for_action and pnl < 0.0 and pf_value < self.config.weak_profit_factor:
            return "quarantine_official_paper_until_edge_review"
        if closed >= self.config.min_closed_for_action and pnl < 0.0:
            return "paper_review"
        if closed >= self.config.min_closed_for_action and pnl > 0.0 and pf_value >= 1.2:
            return "eligible_for_more_observation"
        return "collect_more_data"

    def _primary_findings(self, rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
        findings = []
        metrics = self._metrics(rows)
        cause_counts = self._cause_counts(rows, limit=5)
        if _safe_float(metrics.get("net_pnl_eur")) < 0.0:
            findings.append(
                {
                    "severity": "high",
                    "finding": "realized_paper_pnl_negative",
                    "evidence": {
                        "net_pnl_eur": metrics.get("net_pnl_eur"),
                        "profit_factor": metrics.get("profit_factor"),
                        "win_rate": metrics.get("win_rate"),
                    },
                    "recommended_action": "do_not_promote_to_live",
                }
            )
        if cause_counts:
            top_cause = next(iter(cause_counts.items()))
            findings.append(
                {
                    "severity": "medium",
                    "finding": "dominant_loss_cause",
                    "evidence": {"cause": top_cause[0], "count": top_cause[1]},
                    "recommended_action": "prioritize_this_before_more_tuning",
                }
            )
        if _safe_float(metrics.get("fees_eur")) > abs(_safe_float(metrics.get("net_pnl_eur"))):
            findings.append(
                {
                    "severity": "medium",
                    "finding": "fees_material_vs_net_pnl",
                    "evidence": {
                        "fees_eur": metrics.get("fees_eur"),
                        "net_pnl_eur": metrics.get("net_pnl_eur"),
                    },
                    "recommended_action": "review_maker_taker_and_trade_frequency",
                }
            )
        return findings
