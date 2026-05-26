"""Read-only market-data quality diagnostics for AUTOBOT.

This module does not change trading decisions.  It explains whether signals
are based on fresh prices and a usable order book before microstructure logic
is trusted.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float, minimum: float = 0.0) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    if value < minimum:
        return default
    return value


def _symbol_key(value: Any) -> str:
    return str(value or "").upper().replace("/", "").replace("-", "").strip()


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _age_ms(value: Any, now: datetime) -> float | None:
    timestamp = _parse_timestamp(value)
    if timestamp is None:
        return None
    return max(0.0, (now - timestamp.astimezone(timezone.utc)).total_seconds() * 1000.0)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class MarketDataQualityEngine:
    """Builds a compact, operator-facing quality snapshot per symbol."""

    def __init__(
        self,
        *,
        require_book_for_microstructure: bool | None = None,
        max_price_age_ms: float | None = None,
        max_book_age_ms: float | None = None,
    ) -> None:
        self.require_book_for_microstructure = (
            _env_bool("MICROSTRUCTURE_REQUIRE_BOOK", True)
            if require_book_for_microstructure is None
            else bool(require_book_for_microstructure)
        )
        self.max_price_age_ms = (
            _env_float("MARKET_DATA_MAX_PRICE_AGE_MS", 30_000.0, 1.0)
            if max_price_age_ms is None
            else float(max_price_age_ms)
        )
        self.max_book_age_ms = (
            _env_float("MICROSTRUCTURE_MAX_BOOK_AGE_MS", 5_000.0, 1.0)
            if max_book_age_ms is None
            else float(max_book_age_ms)
        )

    def build_snapshot(
        self,
        *,
        orchestrator: Any,
        instances: Iterable[Mapping[str, Any]] | None = None,
        paper_mode: bool | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        rows = list(instances) if instances is not None else self._instances_from_orchestrator(orchestrator)
        ws = self._websocket_snapshot(orchestrator)
        by_symbol: dict[str, dict[str, Any]] = {}

        for row in rows:
            symbol = _symbol_key(row.get("symbol") or row.get("market") or row.get("pair"))
            if not symbol:
                continue
            current = by_symbol.setdefault(symbol, self._empty_symbol(symbol))
            current["instances"] += 1
            price = _safe_float(row.get("last_price"), current.get("last_price") or 0.0)
            if price > 0.0:
                current["last_price"] = price
                current["price_ok"] = True

            warmup = row.get("warmup") if isinstance(row.get("warmup"), Mapping) else {}
            current["price_samples"] = max(
                int(current.get("price_samples") or 0),
                int(_safe_float(warmup.get("price_samples"), 0.0)),
            )
            tick = row.get("last_tick") if isinstance(row.get("last_tick"), Mapping) else {}
            age = _age_ms(tick.get("timestamp") or row.get("last_price_at"), now)
            if age is not None:
                previous = current.get("price_age_ms")
                current["price_age_ms"] = age if previous is None else min(float(previous), age)

        ofi = getattr(orchestrator, "ofi", None)
        for symbol, row in by_symbol.items():
            book = self._book_snapshot(ofi, symbol)
            row["book"] = book
            row["book_ok"] = bool(book.get("has_book")) and _safe_float(book.get("age_ms"), 0.0) <= self.max_book_age_ms
            row["microstructure_usable"] = row["book_ok"]
            blockers: list[str] = []

            if not row["price_ok"]:
                blockers.append("price_missing")
            elif row.get("price_age_ms") is not None and float(row["price_age_ms"]) > self.max_price_age_ms:
                blockers.append("price_stale")

            if self.require_book_for_microstructure:
                if not book.get("has_book"):
                    book_reason = str(book.get("reason") or "unavailable")
                    blockers.append(
                        book_reason
                        if book_reason.startswith("book_") or book_reason == "invalid_book"
                        else f"book_{book_reason}"
                    )
                elif not row["book_ok"]:
                    blockers.append("book_stale")

            if bool(ws.get("backpressure_active")):
                row["warnings"].append("websocket_backpressure_active")

            row["blockers"] = blockers
            row["status"] = "healthy" if not blockers else "blocked"
            if blockers and (blockers[0].startswith("book_") or blockers[0] == "invalid_book"):
                row["recommended_action"] = "verify_order_book_subscription_and_pair_mapping"
            elif blockers:
                row["recommended_action"] = "wait_for_fresh_market_data"
            else:
                row["recommended_action"] = "eligible_for_microstructure_checks"

        symbols = sorted(by_symbol.values(), key=lambda item: item["symbol"])
        summary = {
            "symbols": len(symbols),
            "healthy_symbols": sum(1 for item in symbols if item["status"] == "healthy"),
            "blocked_symbols": sum(1 for item in symbols if item["status"] != "healthy"),
            "price_missing": sum(1 for item in symbols if "price_missing" in item["blockers"]),
            "book_missing_or_invalid": sum(
                1
                for item in symbols
                if any(str(reason).startswith("book_") or str(reason) == "invalid_book" for reason in item["blockers"])
            ),
            "backpressure_active": bool(ws.get("backpressure_active")),
        }

        if summary["book_missing_or_invalid"] == summary["symbols"] and summary["symbols"]:
            global_action = "order_book_feed_not_usable_for_any_symbol"
        elif summary["blocked_symbols"]:
            global_action = "inspect_blocked_symbols_before_trading"
        else:
            global_action = "market_data_quality_ok"

        return {
            "timestamp": now.isoformat(),
            "mode": "paper" if paper_mode else "live" if paper_mode is False else "unknown",
            "config": {
                "require_book_for_microstructure": self.require_book_for_microstructure,
                "max_price_age_ms": self.max_price_age_ms,
                "max_book_age_ms": self.max_book_age_ms,
            },
            "websocket": ws,
            "recovery": self._recovery_snapshot(orchestrator, ofi),
            "summary": summary,
            "recommended_action": global_action,
            "symbols": symbols,
        }

    @staticmethod
    def _empty_symbol(symbol: str) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "instances": 0,
            "last_price": None,
            "price_ok": False,
            "price_age_ms": None,
            "price_samples": 0,
            "book_ok": False,
            "microstructure_usable": False,
            "warnings": [],
            "blockers": [],
            "status": "unknown",
        }

    @staticmethod
    def _instances_from_orchestrator(orchestrator: Any) -> list[Mapping[str, Any]]:
        getter = getattr(orchestrator, "get_instances_snapshot", None)
        if callable(getter):
            try:
                data = getter()
                if isinstance(data, list):
                    return [row for row in data if isinstance(row, Mapping)]
            except Exception:
                return []
        return []

    @staticmethod
    def _websocket_snapshot(orchestrator: Any) -> dict[str, Any]:
        dispatcher = getattr(orchestrator, "ring_dispatcher", None) or getattr(orchestrator, "ws_client", None)
        getter = getattr(dispatcher, "get_health_snapshot", None)
        if callable(getter):
            try:
                snapshot = getter()
                if isinstance(snapshot, dict):
                    return dict(snapshot)
            except Exception:
                return {"available": False, "connected": False, "reason": "snapshot_error"}
        return {"available": False, "connected": False, "reason": "websocket_unavailable"}

    @staticmethod
    def _book_snapshot(ofi: Any, symbol: str) -> dict[str, Any]:
        if ofi is None:
            return {"symbol": symbol, "has_book": False, "reason": "ofi_unavailable"}
        getter = getattr(ofi, "get_quality_snapshot", None) or getattr(ofi, "get_snapshot", None)
        if not callable(getter):
            return {"symbol": symbol, "has_book": False, "reason": "snapshot_unavailable"}
        try:
            snapshot = getter(symbol)
            if hasattr(snapshot, "to_dict"):
                return dict(snapshot.to_dict())
            if isinstance(snapshot, dict):
                return dict(snapshot)
        except Exception:
            return {"symbol": symbol, "has_book": False, "reason": "snapshot_error"}
        return {"symbol": symbol, "has_book": False, "reason": "snapshot_invalid"}

    @staticmethod
    def _recovery_snapshot(orchestrator: Any, ofi: Any) -> dict[str, Any]:
        runtime = getattr(orchestrator, "_order_book_recovery_stats", {})
        if not isinstance(runtime, Mapping):
            runtime = {}
        ofi_recovery: dict[str, Any] = {}
        getter = getattr(ofi, "get_recovery_snapshot", None)
        if callable(getter):
            try:
                raw = getter()
                if isinstance(raw, dict):
                    ofi_recovery = raw
            except Exception:
                ofi_recovery = {"status": "snapshot_error"}
        return {
            "runtime": dict(runtime),
            "ofi": ofi_recovery,
        }
