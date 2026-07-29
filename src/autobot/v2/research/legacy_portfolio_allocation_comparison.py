"""Research-only comparison of canonical and legacy portfolio allocations.

The runtime ``PortfolioAllocator`` predates the contract-driven research
portfolio path.  This module intentionally does not import it, the
orchestrator, the router, or the paper engine.  It accepts only a frozen
``TargetPortfolio`` and scalar legacy-plan facts, then produces an auditable
alignment report.  The result cannot allocate capital or authorize an order.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

from autobot.v2.contracts import TargetPortfolio


class LegacyAllocationComparisonError(ValueError):
    """Raised when a comparison input is ambiguous or economically invalid."""


@dataclass(frozen=True)
class LegacyAllocationComparison:
    """Non-authorizing difference between canonical and legacy allocations."""

    decision_id: str
    reference_capital_eur: float
    canonical_notionals_eur: Mapping[str, float]
    legacy_notionals_eur: Mapping[str, float]
    canonical_reserve_cash_eur: float
    legacy_reserve_cash_eur: float
    per_symbol_delta_eur: Mapping[str, float]
    target_only_symbols: tuple[str, ...]
    legacy_only_symbols: tuple[str, ...]
    status: str
    reasons: tuple[str, ...]
    research_only: bool = True
    paper_capital_allowed: bool = False
    live_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.research_only or self.paper_capital_allowed or self.live_allowed:
            raise LegacyAllocationComparisonError("legacy allocation comparison is research-only")
        if not str(self.decision_id).strip():
            raise LegacyAllocationComparisonError("decision_id is required")
        if not math.isfinite(float(self.reference_capital_eur)) or float(self.reference_capital_eur) <= 0.0:
            raise LegacyAllocationComparisonError("reference_capital_eur must be positive and finite")
        if self.status not in {"ALIGNED_FOR_RESEARCH_ONLY", "DIVERGENCE_REVIEW_REQUIRED"}:
            raise LegacyAllocationComparisonError("unsupported comparison status")


def compare_target_portfolio_to_legacy_allocation(
    target: TargetPortfolio,
    *,
    reference_capital_eur: float,
    legacy_symbol_caps: Mapping[str, float],
    legacy_reserve_cash_eur: float,
    tolerance_eur: float = 0.01,
) -> LegacyAllocationComparison:
    """Compare explicit allocation facts without importing or changing runtime.

    Symbols are normalized only by trimming and upper-casing.  No quote, venue
    or market conversion is inferred.  Any difference stays a review finding,
    never an instruction to mutate the legacy allocation plan.
    """

    if not isinstance(target, TargetPortfolio):
        raise LegacyAllocationComparisonError("target must be a TargetPortfolio")
    capital = float(reference_capital_eur)
    reserve = float(legacy_reserve_cash_eur)
    tolerance = float(tolerance_eur)
    if not math.isfinite(capital) or capital <= 0.0:
        raise LegacyAllocationComparisonError("reference_capital_eur must be positive and finite")
    if not math.isfinite(reserve) or reserve < 0.0:
        raise LegacyAllocationComparisonError("legacy_reserve_cash_eur must be finite and non-negative")
    if not math.isfinite(tolerance) or tolerance < 0.0:
        raise LegacyAllocationComparisonError("tolerance_eur must be finite and non-negative")

    canonical = {
        _symbol(symbol): float(weight) * capital
        for symbol, weight in target.target_weights.items()
    }
    legacy: dict[str, float] = {}
    for symbol, raw_notional in legacy_symbol_caps.items():
        normalized = _symbol(symbol)
        if normalized in legacy:
            raise LegacyAllocationComparisonError("legacy_symbol_caps contain duplicate normalized symbols")
        notional = float(raw_notional)
        if not math.isfinite(notional) or notional < 0.0:
            raise LegacyAllocationComparisonError("legacy symbol caps must be finite and non-negative")
        legacy[normalized] = notional

    canonical_symbols = set(canonical)
    legacy_symbols = set(legacy)
    target_only = tuple(sorted(canonical_symbols - legacy_symbols))
    legacy_only = tuple(sorted(legacy_symbols - canonical_symbols))
    deltas = {
        symbol: round(legacy.get(symbol, 0.0) - canonical.get(symbol, 0.0), 12)
        for symbol in sorted(canonical_symbols | legacy_symbols)
    }
    reasons: list[str] = []
    if target_only:
        reasons.append("canonical_target_symbols_missing_from_legacy")
    if legacy_only:
        reasons.append("legacy_symbols_absent_from_canonical_target")
    if any(abs(delta) > tolerance for delta in deltas.values()):
        reasons.append("per_symbol_notional_divergence")
    canonical_reserve = float(target.reserve_cash_weight) * capital
    if abs(reserve - canonical_reserve) > tolerance:
        reasons.append("reserve_cash_divergence")
    status = "ALIGNED_FOR_RESEARCH_ONLY" if not reasons else "DIVERGENCE_REVIEW_REQUIRED"

    return LegacyAllocationComparison(
        decision_id=target.decision_id,
        reference_capital_eur=capital,
        canonical_notionals_eur={key: canonical[key] for key in sorted(canonical)},
        legacy_notionals_eur={key: legacy[key] for key in sorted(legacy)},
        canonical_reserve_cash_eur=canonical_reserve,
        legacy_reserve_cash_eur=reserve,
        per_symbol_delta_eur=deltas,
        target_only_symbols=target_only,
        legacy_only_symbols=legacy_only,
        status=status,
        reasons=tuple(reasons),
    )


def _symbol(value: object) -> str:
    normalized = str(value).strip().upper()
    if not normalized:
        raise LegacyAllocationComparisonError("allocation symbol is required")
    return normalized
