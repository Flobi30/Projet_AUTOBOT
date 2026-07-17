"""Shared, research-only contract for verified Kraken Futures basis rows.

Basis must never be inferred by mixing AUTOBOT's EUR spot execution symbols
with USD perpetual-market data.  These constants make the two explicitly
verified sources available to the collector and point-in-time feature builder
without permitting an implicit currency conversion.
"""

from __future__ import annotations

from typing import Any, Mapping


MARK_INDEX_SAME_QUOTE = "MARK_INDEX_SAME_QUOTE"
KRAKEN_FUTURES_FUTURE_BASIS = "KRAKEN_FUTURES_FUTURE_BASIS"
VERIFIED_BASIS_CONFIDENCE_STATUSES = frozenset(
    {
        MARK_INDEX_SAME_QUOTE,
        KRAKEN_FUTURES_FUTURE_BASIS,
    }
)


def is_verified_basis_confidence(value: object) -> bool:
    """Return whether ``value`` is an explicitly same-quote basis source."""

    return str(value or "").strip() in VERIFIED_BASIS_CONFIDENCE_STATUSES


def accepted_basis_confidence_statuses(contract: Mapping[str, Any]) -> frozenset[str]:
    """Read a snapshot contract while keeping v1 manifests compatible.

    Older manifests carry a single ``accepted_confidence_status``.  Newer
    manifests use an explicit set so the exchange-provided future-basis series
    can be used without weakening the same-quote prohibition.
    """

    raw_values = contract.get("accepted_confidence_statuses")
    if isinstance(raw_values, (list, tuple, set, frozenset)):
        return frozenset(
            str(value).strip() for value in raw_values if str(value).strip()
        )
    legacy = str(contract.get("accepted_confidence_status") or "").strip()
    return frozenset({legacy}) if legacy else frozenset()


def basis_contract_metadata(*, invalid_or_unverified_rows_excluded: int) -> dict[str, Any]:
    """Return the immutable same-quote policy persisted with a snapshot."""

    return {
        "calculation_methods": [
            "mark_over_index_same_quote",
            "kraken_futures_future_basis_relative_to_bps",
        ],
        # Kept for readers of the v1 contract.  New readers must inspect the
        # explicit plural field below.
        "accepted_confidence_status": MARK_INDEX_SAME_QUOTE,
        "accepted_confidence_statuses": sorted(VERIFIED_BASIS_CONFIDENCE_STATUSES),
        "same_quote_required": True,
        "implicit_usd_eur_conversion_allowed": False,
        "invalid_or_unverified_rows_excluded": int(invalid_or_unverified_rows_excluded),
    }
