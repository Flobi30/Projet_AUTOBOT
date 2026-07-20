"""Explicit runtime policy for strategies retained only for research.

Grid code and historical records stay available for reproducible research, but
dynamic_grid is deliberately absent from runtime routing and paper execution.
"""

from __future__ import annotations

import os
import math
from datetime import datetime, timezone
from typing import Any, Iterable


GRID_RUNTIME_RETIRED_REASON = "grid_retired_research_only"
GRID_STRATEGY_ALIASES = frozenset({"dynamic_grid", "grid", "grid_core"})
RETIRED_RUNTIME_ENGINES = GRID_STRATEGY_ALIASES
LEGACY_UNATTRIBUTED_STRATEGY_ID = "legacy_unattributed"
EXECUTION_MODE_SHADOW_PAPER = "shadow_paper"
EXECUTION_MODE_PAPER_CAPITAL = "paper_capital"
EXECUTION_MODE_LEGACY_UNSPECIFIED = "legacy_unspecified"
REPORTABLE_PAPER_EXECUTION_MODES = frozenset(
    {EXECUTION_MODE_SHADOW_PAPER, EXECUTION_MODE_PAPER_CAPITAL}
)
SHADOW_PAPER_OBSERVATION_STRATEGIES = frozenset(
    {
        "trend_momentum",
        "mean_reversion",
        "high_conviction_swing",
        "opportunity_scoring",
    }
)


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


def normalize_execution_mode(execution_mode: Any) -> str:
    normalized = str(execution_mode or "").strip().lower()
    if not normalized:
        return EXECUTION_MODE_LEGACY_UNSPECIFIED
    if normalized in {"paper", "official_paper", "paper_official"}:
        return EXECUTION_MODE_PAPER_CAPITAL
    if normalized in {"shadow", "paper_shadow", "shadow_signal_mirror"}:
        return EXECUTION_MODE_SHADOW_PAPER
    return normalized


def official_paper_strategy_block_reason(strategy_id: Any) -> str | None:
    normalized = normalize_strategy_id(strategy_id)
    if not normalized:
        return "strategy_id_required"
    if normalized.lower() == LEGACY_UNATTRIBUTED_STRATEGY_ID:
        return "strategy_id_required"
    if is_runtime_engine_retired(normalized):
        return GRID_RUNTIME_RETIRED_REASON
    return None


def shadow_paper_strategy_block_reason(strategy_id: Any) -> str | None:
    normalized = normalize_strategy_id(strategy_id)
    base_reason = official_paper_strategy_block_reason(normalized)
    if base_reason is not None:
        return base_reason
    if normalized not in SHADOW_PAPER_OBSERVATION_STRATEGIES:
        return "shadow_paper_strategy_not_allowed"
    return None


def canonical_order_append_block_reason(
    strategy_id: Any,
    *,
    decision_id: Any,
    signal_id: Any,
) -> str | None:
    """Return why a new persisted order lacks canonical provenance."""

    base_reason = official_paper_strategy_block_reason(strategy_id)
    if base_reason is not None:
        return base_reason
    if not normalize_strategy_id(decision_id):
        return "decision_id_required"
    if not normalize_strategy_id(signal_id):
        return "signal_id_required"
    return None


def trade_ledger_append_block_reason(
    strategy_id: Any,
    *,
    execution_mode: Any = None,
    paper_capital_gate_attested: bool = False,
) -> str | None:
    """Return why a paper ledger row must not be written.

    ``legacy_unspecified`` preserves compatibility for historical/test writers,
    but official P1/P2 reporting ignores it. New runtime/research writers must
    choose ``shadow_paper`` or ``paper_capital`` explicitly.
    """

    mode = normalize_execution_mode(execution_mode)
    if mode == EXECUTION_MODE_SHADOW_PAPER:
        return shadow_paper_strategy_block_reason(strategy_id)
    base_reason = official_paper_strategy_block_reason(strategy_id)
    if base_reason is not None:
        return base_reason
    if mode == EXECUTION_MODE_PAPER_CAPITAL and not paper_capital_gate_attested:
        return "paper_capital_requires_promotion_gate"
    if mode == EXECUTION_MODE_LEGACY_UNSPECIFIED:
        return None
    if mode not in REPORTABLE_PAPER_EXECUTION_MODES:
        return f"invalid_execution_mode:{mode}"
    return None


def canonical_trade_ledger_append_block_reason(
    strategy_id: Any,
    *,
    decision_id: Any,
    signal_id: Any,
    fees: Any,
    slippage_bps: Any,
    execution_mode: Any,
    paper_capital_gate_attested: bool = False,
) -> str | None:
    """Return why a *new* runtime ledger row lacks canonical provenance.

    Historical rows remain preserved in SQLite but must not be created through
    the current persistence API.  A future writer must make an explicit
    execution-mode choice and carry the minimum evidence required to audit
    strategy, decision, signal and transaction costs end-to-end.
    """

    if not normalize_strategy_id(decision_id):
        return "decision_id_required"
    if not normalize_strategy_id(signal_id):
        return "signal_id_required"
    if execution_mode is None or not str(execution_mode).strip():
        return "execution_mode_required"
    normalized_mode = normalize_execution_mode(execution_mode)
    if normalized_mode == EXECUTION_MODE_LEGACY_UNSPECIFIED:
        return "execution_mode_required"
    try:
        parsed_fees = float(fees)
    except (TypeError, ValueError):
        return "fees_required"
    if not math.isfinite(parsed_fees) or parsed_fees < 0.0:
        return "fees_invalid"
    try:
        parsed_slippage = float(slippage_bps)
    except (TypeError, ValueError):
        return "slippage_bps_required"
    if not math.isfinite(parsed_slippage):
        return "slippage_bps_invalid"
    return trade_ledger_append_block_reason(
        strategy_id,
        execution_mode=normalized_mode,
        paper_capital_gate_attested=paper_capital_gate_attested,
    )


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
