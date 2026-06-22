"""Explicit runtime policy for strategies retained only for research.

Grid code and historical records stay available for reproducible research, but
dynamic_grid is deliberately absent from runtime routing and paper execution.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable


GRID_RUNTIME_RETIRED_REASON = "grid_retired_research_only"
RETIRED_RUNTIME_ENGINES = frozenset({"dynamic_grid"})


def is_runtime_engine_retired(engine: Any) -> bool:
    return str(engine or "").strip().lower() in RETIRED_RUNTIME_ENGINES


def retired_grid_snapshot(symbols: Iterable[Any] = ()) -> dict[str, Any]:
    watched_symbols = sorted({str(symbol).strip() for symbol in symbols if str(symbol).strip()})
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "engine": "dynamic_grid",
        "mode": "retired_research_only",
        "status": "retired_from_runtime",
        "enabled": False,
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
