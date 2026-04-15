"""Universe manager for AUTOBOT v2.

Lot 1 scope:
- Dedicated state layer separating supported / eligible / ranked / websocket-active / actively-traded universes.
- Lightweight, in-memory, deterministic behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Sequence, Set, Tuple

from .markets import MARKETS, MarketType, get_market_config


@dataclass
class UniverseSnapshot:
    """Immutable view of the universe state."""

    supported: frozenset[str]
    eligible: frozenset[str]
    ranked: Tuple[str, ...]
    scored: Dict[str, Dict[str, Any]]
    websocket_active: frozenset[str]
    actively_traded: frozenset[str]


@dataclass
class UniverseManager:
    """Manages separated market universes for selection/runtime concerns."""

    max_supported: int
    max_eligible: int
    enable_forex: bool
    _supported: Set[str] = field(default_factory=set, init=False)
    _eligible: Set[str] = field(default_factory=set, init=False)
    _ranked: List[str] = field(default_factory=list, init=False)
    _scored: Dict[str, Dict[str, Any]] = field(default_factory=dict, init=False)
    _websocket_active: Set[str] = field(default_factory=set, init=False)
    _actively_traded: Set[str] = field(default_factory=set, init=False)

    def initialize(self, preferred_symbols: Sequence[str] | None = None) -> None:
        """Bootstrap supported/eligible universes from known market configs."""
        ordered = self._ordered_supported_candidates(preferred_symbols)
        self._supported = set(ordered[: self.max_supported])
        self._eligible = set(ordered[: min(self.max_eligible, len(ordered))])
        self._ranked = [s for s in ordered if s in self._eligible]
        self._ranked = [s for s in self._ranked if s in self._eligible]
        self._scored = {s: v for s, v in self._scored.items() if s in self._eligible}
        self._websocket_active.intersection_update(self._supported)
        self._actively_traded.intersection_update(self._supported)

    def update_ranked_universe(self, ranked_symbols: Iterable[str]) -> None:
        """Update ranked/scored universe from an external scoring pipeline."""
        ranked = []
        for symbol in ranked_symbols:
            if symbol in self._eligible and symbol not in ranked:
                ranked.append(symbol)
            if len(ranked) >= self.max_eligible:
                break
        self._ranked = ranked

    def update_scored_universe(self, scored: Dict[str, Dict[str, Any]]) -> None:
        """Update scored/ranked metadata for eligible universe only."""
        filtered = {}
        for symbol, payload in scored.items():
            if symbol in self._eligible:
                filtered[symbol] = dict(payload)
        self._scored = filtered

    def set_eligible_universe(self, symbols: Iterable[str]) -> None:
        """Override eligible universe while respecting supported/caps."""
        eligible = []
        for symbol in symbols:
            if symbol in self._supported and symbol not in eligible:
                eligible.append(symbol)
            if len(eligible) >= self.max_eligible:
                break
        self._eligible = set(eligible)
        self._ranked = [s for s in self._ranked if s in self._eligible]
        self._scored = {s: v for s, v in self._scored.items() if s in self._eligible}
        self._websocket_active.intersection_update(self._eligible)

    def mark_websocket_active(self, symbols: Iterable[str]) -> None:
        self._websocket_active = {s for s in symbols if s in self._eligible}

    def mark_actively_traded(self, symbols: Iterable[str]) -> None:
        self._actively_traded = {s for s in symbols if s in self._eligible}

    def get_supported_universe(self) -> Set[str]:
        return set(self._supported)

    def get_eligible_universe(self) -> Set[str]:
        return set(self._eligible)

    def get_ranked_universe(self) -> List[str]:
        return list(self._ranked)

    def get_scored_universe(self) -> Dict[str, Dict[str, Any]]:
        return {s: dict(v) for s, v in self._scored.items()}

    def get_websocket_active_universe(self) -> Set[str]:
        return set(self._websocket_active)

    def get_actively_traded_universe(self) -> Set[str]:
        return set(self._actively_traded)

    def snapshot(self) -> UniverseSnapshot:
        return UniverseSnapshot(
            supported=frozenset(self._supported),
            eligible=frozenset(self._eligible),
            ranked=tuple(self._ranked),
            scored={s: dict(v) for s, v in self._scored.items()},
            websocket_active=frozenset(self._websocket_active),
            actively_traded=frozenset(self._actively_traded),
        )

    def _ordered_supported_candidates(self, preferred_symbols: Sequence[str] | None = None) -> List[str]:
        ordered: List[str] = []
        if preferred_symbols:
            for symbol in preferred_symbols:
                if self._is_symbol_allowed(symbol) and symbol not in ordered:
                    ordered.append(symbol)

        for symbol in MARKETS:
            if self._is_symbol_allowed(symbol) and symbol not in ordered:
                ordered.append(symbol)
        return ordered

    def _is_symbol_allowed(self, symbol: str) -> bool:
        config = get_market_config(symbol)
        if config is None:
            return False
        if config.market_type == MarketType.FOREX and not self.enable_forex:
            return False
        return True
