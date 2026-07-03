"""Shared paper ledger quality guards for research/reporting.

These helpers are read-only. They classify loaded ``TradeRecord`` objects so
diagnostic and promotion-adjacent reports do not accidentally trust rows whose
ledger reconstruction is incomplete or anomalous.
"""

from __future__ import annotations

from collections import Counter
from typing import Mapping, Sequence

from autobot.v2.research.trade_journal import TradeRecord


CRITICAL_LEDGER_WARNING_REASONS = ("opening_leg_missing", "slippage_bps_anomaly")


def critical_ledger_warning_reason(record: TradeRecord) -> str | None:
    """Return a reason when a loaded trade is unsafe for official decisions."""

    if bool(record.metadata.get("opening_leg_missing")):
        return "opening_leg_missing"
    slippage = record.metadata.get("slippage")
    if isinstance(slippage, Mapping) and bool(slippage.get("anomaly")):
        return "slippage_bps_anomaly"
    return None


def has_critical_ledger_warning(record: TradeRecord) -> bool:
    return critical_ledger_warning_reason(record) is not None


def critical_warning_counts(records: Sequence[TradeRecord]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for record in records:
        reason = critical_ledger_warning_reason(record)
        if reason is not None:
            counter[reason] += 1
    return dict(sorted(counter.items()))


def loader_warning_counts(warnings: Sequence[str]) -> dict[str, int]:
    """Count loader warning prefixes such as ``opening_leg_missing``."""

    counter: Counter[str] = Counter()
    for warning in warnings:
        prefix = str(warning).split(":", 1)[0] if warning else "unknown"
        counter[prefix] += 1
    return dict(sorted(counter.items()))
