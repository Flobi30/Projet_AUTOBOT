"""Trade-level reconciliation between official paper closes and shadow labs.

This module is read-only.  It exists to explain why the official paper ledger
can lose money while one of the shadow engines reports a profitable setup.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

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
class ShadowTradeSource:
    engine: str
    table: str
    db_path: str


@dataclass(frozen=True)
class StrategyTradeReconciliationConfig:
    window_hours: int = 168
    official_limit: int = 250
    shadow_limit: int = 1_000
    match_tolerance_minutes: int = 180
    fee_delta_bps_warn: float = 8.0
    return_delta_bps_warn: float = 20.0

    @classmethod
    def from_env(cls) -> "StrategyTradeReconciliationConfig":
        return cls(
            window_hours=_env_int("STRATEGY_TRADE_RECONCILIATION_WINDOW_HOURS", 168, 1, 8_760),
            official_limit=_env_int("STRATEGY_TRADE_RECONCILIATION_OFFICIAL_LIMIT", 250, 1, 20_000),
            shadow_limit=_env_int("STRATEGY_TRADE_RECONCILIATION_SHADOW_LIMIT", 1_000, 1, 100_000),
            match_tolerance_minutes=_env_int(
                "STRATEGY_TRADE_RECONCILIATION_MATCH_TOLERANCE_MINUTES", 180, 1, 10_080
            ),
            fee_delta_bps_warn=_env_float("STRATEGY_TRADE_RECONCILIATION_FEE_DELTA_BPS_WARN", 8.0, 0.0, 500.0),
            return_delta_bps_warn=_env_float(
                "STRATEGY_TRADE_RECONCILIATION_RETURN_DELTA_BPS_WARN", 20.0, 0.0, 2_000.0
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_hours": self.window_hours,
            "official_limit": self.official_limit,
            "shadow_limit": self.shadow_limit,
            "match_tolerance_minutes": self.match_tolerance_minutes,
            "fee_delta_bps_warn": self.fee_delta_bps_warn,
            "return_delta_bps_warn": self.return_delta_bps_warn,
        }


class StrategyTradeReconciliationEngine:
    """Compare recent official paper closes with nearby shadow closes."""

    DEFAULT_SHADOW_SOURCES = {
        "dynamic_grid": ("data/setup_shadow_lab.db", "setup_shadow_trades"),
        "trend_momentum": ("data/trend_shadow_lab.db", "trend_shadow_trades"),
        "mean_reversion": ("data/mean_reversion_shadow_lab.db", "mean_reversion_shadow_trades"),
    }

    def __init__(self, config: StrategyTradeReconciliationConfig | None = None) -> None:
        self.config = config or StrategyTradeReconciliationConfig.from_env()

    def build_snapshot(
        self,
        *,
        state_db_path: Any,
        paper_mode: bool,
        shadow_db_paths: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.config.window_hours)
        official_rows, official_source = self._load_official_closes(str(state_db_path or ""), cutoff)
        shadow_rows, shadow_sources = self._load_shadow_closes(shadow_db_paths or {}, cutoff)
        matched_rows = self._match_rows(official_rows, shadow_rows)
        summary = self._summary(matched_rows, official_rows, shadow_rows)

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "paper" if paper_mode else "live_observation",
            "paper_mode": paper_mode,
            "paper_only": True,
            "live_promotion_allowed": False,
            "config": self.config.to_dict(),
            "summary": summary,
            "rows": matched_rows,
            "data_sources": {
                "official": official_source,
                "shadow": shadow_sources,
            },
            "message": (
                "Trade-level reconciliation uses nearest closes by symbol/time. "
                "It is an audit signal, not proof that both engines took the exact same trade."
            ),
        }

    def _load_official_closes(self, db_path: str, cutoff: datetime) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        source = {"path": db_path, "status": "missing", "loaded": 0, "table": "trade_ledger"}
        if not db_path or not Path(db_path).exists():
            return [], source

        try:
            with _read_only_conn(db_path) as conn:
                tables = _table_names(conn)
                if "trade_ledger" not in tables:
                    source["status"] = "trade_ledger_missing"
                    return [], source
                has_positions = "positions" in tables
                query = """
                    SELECT
                        tl.id,
                        tl.trade_id,
                        tl.position_id,
                        tl.instance_id,
                        tl.symbol,
                        tl.side,
                        tl.expected_price,
                        tl.executed_price,
                        tl.volume,
                        tl.fees,
                        tl.slippage_bps,
                        tl.realized_pnl,
                        tl.decision_id,
                        tl.signal_id,
                        tl.execution_liquidity,
                        tl.created_at,
                        p.buy_price AS entry_price,
                        p.open_time AS opened_at,
                        p.strategy AS position_strategy
                    FROM trade_ledger tl
                    LEFT JOIN positions p ON p.id = tl.position_id
                    WHERE tl.is_closing_leg = 1
                      AND tl.created_at >= ?
                    ORDER BY tl.created_at DESC
                    LIMIT ?
                """ if has_positions else """
                    SELECT
                        tl.id,
                        tl.trade_id,
                        tl.position_id,
                        tl.instance_id,
                        tl.symbol,
                        tl.side,
                        tl.expected_price,
                        tl.executed_price,
                        tl.volume,
                        tl.fees,
                        tl.slippage_bps,
                        tl.realized_pnl,
                        tl.decision_id,
                        tl.signal_id,
                        tl.execution_liquidity,
                        tl.created_at,
                        NULL AS entry_price,
                        NULL AS opened_at,
                        NULL AS position_strategy
                    FROM trade_ledger tl
                    WHERE tl.is_closing_leg = 1
                      AND tl.created_at >= ?
                    ORDER BY tl.created_at DESC
                    LIMIT ?
                """
                rows = [self._official_row(row) for row in conn.execute(query, (cutoff.isoformat(), self.config.official_limit))]
                source.update({"status": "ok", "loaded": len(rows), "positions_joined": has_positions})
                return rows, source
        except Exception as exc:
            source.update({"status": "error", "error": str(exc)[:240]})
            return [], source

    def _load_shadow_closes(
        self,
        shadow_db_paths: Mapping[str, Any],
        cutoff: datetime,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        sources = self._shadow_sources(shadow_db_paths)
        all_rows: list[dict[str, Any]] = []
        source_status: dict[str, Any] = {}

        for source in sources:
            status = {"path": source.db_path, "table": source.table, "status": "missing", "loaded": 0}
            if not source.db_path or not Path(source.db_path).exists():
                source_status[source.engine] = status
                continue
            try:
                with _read_only_conn(source.db_path) as conn:
                    tables = _table_names(conn)
                    if source.table not in tables:
                        status["status"] = "table_missing"
                        source_status[source.engine] = status
                        continue
                    query = f"""
                        SELECT
                            id,
                            symbol,
                            variant,
                            position_id,
                            entry_price,
                            exit_price,
                            volume,
                            notional,
                            fees,
                            realized_pnl,
                            reason,
                            opened_at,
                            closed_at,
                            created_at
                        FROM {source.table}
                        WHERE COALESCE(closed_at, created_at) >= ?
                        ORDER BY COALESCE(closed_at, created_at) DESC
                        LIMIT ?
                    """
                    rows = [
                        self._shadow_row(source.engine, row)
                        for row in conn.execute(query, (cutoff.isoformat(), self.config.shadow_limit))
                    ]
                    all_rows.extend(rows)
                    status.update({"status": "ok", "loaded": len(rows)})
                    source_status[source.engine] = status
            except Exception as exc:
                status.update({"status": "error", "error": str(exc)[:240]})
                source_status[source.engine] = status

        return all_rows, source_status

    def _shadow_sources(self, shadow_db_paths: Mapping[str, Any]) -> list[ShadowTradeSource]:
        result = []
        for engine, (default_path, table) in self.DEFAULT_SHADOW_SOURCES.items():
            path = shadow_db_paths.get(engine, default_path)
            result.append(ShadowTradeSource(engine=engine, table=table, db_path=str(path or default_path)))
        return result

    def _official_row(self, row: sqlite3.Row) -> dict[str, Any]:
        symbol = symbol_key(row["symbol"])
        entry_price = _safe_float(row["entry_price"], 0.0)
        exit_price = _safe_float(row["executed_price"], 0.0)
        volume = _safe_float(row["volume"], 0.0)
        notional = abs(exit_price * volume)
        side = str(row["side"] or "").lower()
        raw_return_bps = ((exit_price - entry_price) / entry_price * 10_000.0) if entry_price > 0.0 else None
        return_bps = -raw_return_bps if raw_return_bps is not None and side == "buy" else raw_return_bps
        fee_bps = (_safe_float(row["fees"]) / notional * 10_000.0) if notional > 0.0 else None
        created_at = _ts(row["created_at"])
        return {
            "id": _safe_int(row["id"]),
            "trade_id": row["trade_id"],
            "position_id": row["position_id"],
            "instance_id": row["instance_id"],
            "symbol": symbol,
            "side": side,
            "entry_price": _round(entry_price) if entry_price > 0.0 else None,
            "exit_price": _round(exit_price),
            "volume": _round(volume, 8),
            "notional_eur": _round(notional),
            "fees_eur": _round(row["fees"]),
            "fee_bps": round(fee_bps, 2) if fee_bps is not None else None,
            "slippage_bps": _round(row["slippage_bps"], 2),
            "realized_pnl_eur": _round(row["realized_pnl"]),
            "return_bps": round(return_bps, 2) if return_bps is not None else None,
            "decision_id": row["decision_id"],
            "signal_id": row["signal_id"],
            "execution_liquidity": row["execution_liquidity"],
            "strategy": row["position_strategy"],
            "opened_at": _ts(row["opened_at"]),
            "closed_at": created_at,
            "_closed_dt": _parse_ts(row["created_at"]),
        }

    def _shadow_row(self, engine: str, row: sqlite3.Row) -> dict[str, Any]:
        symbol = symbol_key(row["symbol"])
        entry_price = _safe_float(row["entry_price"], 0.0)
        exit_price = _safe_float(row["exit_price"], 0.0)
        notional = abs(_safe_float(row["notional"], 0.0))
        if notional <= 0.0:
            notional = abs(exit_price * _safe_float(row["volume"], 0.0))
        return_bps = ((exit_price - entry_price) / entry_price * 10_000.0) if entry_price > 0.0 else None
        fee_bps = (_safe_float(row["fees"]) / notional * 10_000.0) if notional > 0.0 else None
        closed_at_raw = row["closed_at"] or row["created_at"]
        closed_at = _ts(closed_at_raw)
        return {
            "id": _safe_int(row["id"]),
            "engine": engine,
            "symbol": symbol,
            "variant": row["variant"],
            "position_id": row["position_id"],
            "entry_price": _round(entry_price),
            "exit_price": _round(exit_price),
            "volume": _round(row["volume"], 8),
            "notional_eur": _round(notional),
            "fees_eur": _round(row["fees"]),
            "fee_bps": round(fee_bps, 2) if fee_bps is not None else None,
            "realized_pnl_eur": _round(row["realized_pnl"]),
            "return_bps": round(return_bps, 2) if return_bps is not None else None,
            "reason": row["reason"],
            "opened_at": _ts(row["opened_at"]),
            "closed_at": closed_at,
            "_closed_dt": _parse_ts(closed_at_raw),
        }

    def _match_rows(self, official_rows: list[dict[str, Any]], shadow_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        shadow_by_symbol: dict[str, list[dict[str, Any]]] = {}
        for row in shadow_rows:
            shadow_by_symbol.setdefault(str(row.get("symbol")), []).append(row)

        matched = []
        tolerance = timedelta(minutes=self.config.match_tolerance_minutes)
        for official in official_rows:
            official_dt = official.get("_closed_dt")
            candidates = []
            if isinstance(official_dt, datetime):
                for shadow in shadow_by_symbol.get(str(official.get("symbol")), []):
                    shadow_dt = shadow.get("_closed_dt")
                    if not isinstance(shadow_dt, datetime):
                        continue
                    delta = abs(official_dt - shadow_dt)
                    if delta <= tolerance:
                        candidates.append((delta, -_safe_float(shadow.get("realized_pnl_eur")), shadow))
            matched_shadow = sorted(candidates, key=lambda item: (item[0], item[1]))[0][2] if candidates else None
            row = self._comparison_row(official, matched_shadow)
            matched.append(row)
        return matched

    def _comparison_row(
        self,
        official: Mapping[str, Any],
        shadow: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        official_public = self._public_row(official)
        if shadow is None:
            return {
                "symbol": official.get("symbol"),
                "verdict": "no_shadow_match",
                "root_causes": ["no_nearby_shadow_close_for_symbol"],
                "official": official_public,
                "matched_shadow": None,
                "deltas": {},
            }

        shadow_public = self._public_row(shadow)
        official_pnl = _safe_float(official.get("realized_pnl_eur"))
        shadow_pnl = _safe_float(shadow.get("realized_pnl_eur"))
        official_return = official.get("return_bps")
        shadow_return = shadow.get("return_bps")
        official_fee = official.get("fee_bps")
        shadow_fee = shadow.get("fee_bps")
        official_dt = official.get("_closed_dt")
        shadow_dt = shadow.get("_closed_dt")
        time_delta_minutes = None
        if isinstance(official_dt, datetime) and isinstance(shadow_dt, datetime):
            time_delta_minutes = round(abs((official_dt - shadow_dt).total_seconds()) / 60.0, 2)

        deltas = {
            "pnl_delta_eur": round(official_pnl - shadow_pnl, 4),
            "return_delta_bps": (
                round(_safe_float(official_return) - _safe_float(shadow_return), 2)
                if official_return is not None and shadow_return is not None
                else None
            ),
            "fee_delta_bps": (
                round(_safe_float(official_fee) - _safe_float(shadow_fee), 2)
                if official_fee is not None and shadow_fee is not None
                else None
            ),
            "time_delta_minutes": time_delta_minutes,
        }
        verdict, causes = self._verdict(official, shadow, deltas)
        return {
            "symbol": official.get("symbol"),
            "verdict": verdict,
            "root_causes": causes,
            "official": official_public,
            "matched_shadow": shadow_public,
            "deltas": deltas,
        }

    @staticmethod
    def _public_row(row: Mapping[str, Any]) -> dict[str, Any]:
        return {str(key): value for key, value in row.items() if not str(key).startswith("_")}

    def _verdict(
        self,
        official: Mapping[str, Any],
        shadow: Mapping[str, Any],
        deltas: Mapping[str, Any],
    ) -> tuple[str, list[str]]:
        official_pnl = _safe_float(official.get("realized_pnl_eur"))
        shadow_pnl = _safe_float(shadow.get("realized_pnl_eur"))
        causes: list[str] = []

        if official.get("entry_price") is None:
            causes.append("official_entry_missing")

        fee_delta = deltas.get("fee_delta_bps")
        if fee_delta is not None and _safe_float(fee_delta) >= self.config.fee_delta_bps_warn:
            causes.append("official_fee_bps_above_shadow")

        return_delta = deltas.get("return_delta_bps")
        if return_delta is not None and _safe_float(return_delta) <= -self.config.return_delta_bps_warn:
            causes.append("official_return_bps_below_shadow")

        if official_pnl < 0.0 and shadow_pnl > 0.0:
            causes.append("official_loss_shadow_win")
            if "official_fee_bps_above_shadow" in causes or "official_return_bps_below_shadow" in causes:
                return "execution_drag", sorted(set(causes))
            return "official_loss_shadow_win", sorted(set(causes))

        if official_pnl < 0.0 and shadow_pnl <= 0.0:
            causes.append("aligned_negative")
            return "aligned_loss", sorted(set(causes))

        if official_pnl > 0.0 and shadow_pnl > 0.0:
            return "aligned_win", sorted(set(causes)) or ["official_and_shadow_positive"]

        if official_pnl > 0.0 and shadow_pnl < 0.0:
            causes.append("official_better_than_shadow")
            return "official_better", sorted(set(causes))

        return "neutral", sorted(set(causes)) or ["no_clear_divergence"]

    def _summary(
        self,
        comparison_rows: list[Mapping[str, Any]],
        official_rows: list[Mapping[str, Any]],
        shadow_rows: list[Mapping[str, Any]],
    ) -> dict[str, Any]:
        verdict_counts: dict[str, int] = {}
        by_symbol: dict[str, dict[str, Any]] = {}
        matched = 0
        pnl_deltas = []
        return_deltas = []
        fee_deltas = []

        for row in comparison_rows:
            verdict = str(row.get("verdict") or "unknown")
            verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
            official = row.get("official") if isinstance(row.get("official"), Mapping) else {}
            shadow = row.get("matched_shadow") if isinstance(row.get("matched_shadow"), Mapping) else None
            deltas = row.get("deltas") if isinstance(row.get("deltas"), Mapping) else {}
            symbol = str(row.get("symbol") or "UNKNOWN")
            target = by_symbol.setdefault(
                symbol,
                {
                    "symbol": symbol,
                    "official_closes": 0,
                    "matched_shadow_closes": 0,
                    "official_net_pnl_eur": 0.0,
                    "matched_shadow_net_pnl_eur": 0.0,
                    "official_loss_shadow_win": 0,
                    "execution_drag": 0,
                },
            )
            target["official_closes"] += 1
            target["official_net_pnl_eur"] += _safe_float(official.get("realized_pnl_eur"))
            if shadow is not None:
                matched += 1
                target["matched_shadow_closes"] += 1
                target["matched_shadow_net_pnl_eur"] += _safe_float(shadow.get("realized_pnl_eur"))
                if isinstance(deltas.get("pnl_delta_eur"), (int, float)):
                    pnl_deltas.append(float(deltas["pnl_delta_eur"]))
                if isinstance(deltas.get("return_delta_bps"), (int, float)):
                    return_deltas.append(float(deltas["return_delta_bps"]))
                if isinstance(deltas.get("fee_delta_bps"), (int, float)):
                    fee_deltas.append(float(deltas["fee_delta_bps"]))
            if verdict in {"official_loss_shadow_win", "execution_drag"}:
                target["official_loss_shadow_win"] += 1
            if verdict == "execution_drag":
                target["execution_drag"] += 1

        by_symbol_rows = []
        for row in by_symbol.values():
            row["official_net_pnl_eur"] = round(_safe_float(row["official_net_pnl_eur"]), 4)
            row["matched_shadow_net_pnl_eur"] = round(_safe_float(row["matched_shadow_net_pnl_eur"]), 4)
            row["pnl_delta_eur"] = round(row["official_net_pnl_eur"] - row["matched_shadow_net_pnl_eur"], 4)
            by_symbol_rows.append(row)
        by_symbol_rows.sort(key=lambda item: (_safe_int(item.get("official_loss_shadow_win")), -_safe_float(item.get("pnl_delta_eur"))), reverse=True)

        return {
            "official_closes_loaded": len(official_rows),
            "shadow_closes_loaded": len(shadow_rows),
            "matched_count": matched,
            "no_match_count": len(comparison_rows) - matched,
            "official_loss_shadow_win_count": sum(
                1 for row in comparison_rows if row.get("verdict") in {"official_loss_shadow_win", "execution_drag"}
            ),
            "verdict_counts": verdict_counts,
            "avg_pnl_delta_eur": round(sum(pnl_deltas) / len(pnl_deltas), 4) if pnl_deltas else None,
            "avg_return_delta_bps": round(sum(return_deltas) / len(return_deltas), 2) if return_deltas else None,
            "avg_fee_delta_bps": round(sum(fee_deltas) / len(fee_deltas), 2) if fee_deltas else None,
            "requires_attention": sum(
                1 for row in comparison_rows if row.get("verdict") in {"official_loss_shadow_win", "execution_drag", "no_shadow_match"}
            ),
            "by_symbol": by_symbol_rows,
        }
