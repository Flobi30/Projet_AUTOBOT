"""Explicit runtime policy for strategies retained only for research.

Grid code and historical records stay available for reproducible research, but
dynamic_grid is deliberately absent from runtime routing and paper execution.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Iterable


GRID_RUNTIME_RETIRED_REASON = "grid_retired_research_only"
GRID_STRATEGY_ALIASES = frozenset({"dynamic_grid", "grid", "grid_core"})
RETIRED_RUNTIME_ENGINES = GRID_STRATEGY_ALIASES


def grid_runtime_enabled() -> bool:
    raw = os.getenv("GRID_RUNTIME_ENABLED")
    if raw is None:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def is_runtime_engine_retired(engine: Any) -> bool:
    normalized = str(engine or "").strip().lower()
    return normalized in RETIRED_RUNTIME_ENGINES


def normalize_strategy_id(strategy_id: Any) -> str:
    return str(strategy_id or "").strip()


def official_paper_strategy_block_reason(strategy_id: Any) -> str | None:
    normalized = normalize_strategy_id(strategy_id)
    if not normalized:
        return "strategy_id_required"
    if is_runtime_engine_retired(normalized):
        return GRID_RUNTIME_RETIRED_REASON
    return None


def retired_grid_snapshot(symbols: Iterable[Any] = ()) -> dict[str, Any]:
    watched_symbols = sorted({str(symbol).strip() for symbol in symbols if str(symbol).strip()})
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "engine": "dynamic_grid",
        "mode": "retired_research_only",
        "status": "retired_from_runtime",
        "enabled": False,
        "runtime_flag": {
            "name": "GRID_RUNTIME_ENABLED",
            "requested_value": grid_runtime_enabled(),
            "effective_runtime_enabled": False,
        },
        "paper_only": True,
        "live_promotion_allowed": False,
        "writes_official_paper_ledger": False,
        "applies_to_execution": False,
        "reason": GRID_RUNTIME_RETIRED_REASON,
        "summary": {
            "status": "retired_from_runtime",
            "watched_symbols": len(watched_symbols),
            "active_symbols": 0,
            "historical_records_preserved": True,
        },
        "symbols": [],
        "by_symbol": {},
    }
