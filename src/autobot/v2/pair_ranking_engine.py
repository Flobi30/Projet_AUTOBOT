"""Pair ranking engine (Lot 2).

Centralized, explainable, cached ranking for eligible symbols.
The engine is intentionally lightweight and must run on control cadence only.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from .market_analyzer import MarketAnalyzer, get_market_analyzer
from .universe_manager import UniverseManager


@dataclass(frozen=True)
class PairScore:
    symbol: str
    score: float
    explain: Dict[str, float | str]


class PairRankingEngine:
    def __init__(
        self,
        universe_manager: UniverseManager,
        analyzer: Optional[MarketAnalyzer] = None,
        update_seconds: int = 300,
        min_score_activate: float = 55.0,
    ) -> None:
        self.universe_manager = universe_manager
        self.analyzer = analyzer or get_market_analyzer()
        self.update_seconds = max(1, int(update_seconds))
        self.min_score_activate = float(min_score_activate)
        self._last_update_ts = 0.0
        self._cached_scores: Dict[str, PairScore] = {}

    def refresh_if_due(self, now_ts: Optional[float] = None) -> List[PairScore]:
        now = float(now_ts if now_ts is not None else time.monotonic())
        if self._cached_scores and (now - self._last_update_ts) < self.update_seconds:
            return self.get_ranked_pairs()
        return self.refresh(now_ts=now)

    def refresh(self, now_ts: Optional[float] = None) -> List[PairScore]:
        now = float(now_ts if now_ts is not None else time.monotonic())
        eligible = sorted(self.universe_manager.get_eligible_universe())
        scores: Dict[str, PairScore] = {}

        for symbol in eligible:
            metrics = self.analyzer.analyze_market(symbol)
            if not metrics:
                continue
            pair_score = self._score_symbol(symbol, metrics)
            scores[symbol] = pair_score

        ranked = sorted(scores.values(), key=lambda p: p.score, reverse=True)
        self._cached_scores = {p.symbol: p for p in ranked}
        self._last_update_ts = now

        self.universe_manager.update_scored_universe(
            {
                p.symbol: {
                    "score": p.score,
                    **p.explain,
                }
                for p in ranked
            }
        )
        self.universe_manager.update_ranked_universe([p.symbol for p in ranked])
        return ranked

    def get_ranked_pairs(self) -> List[PairScore]:
        ranked = list(self._cached_scores.values())
        return sorted(ranked, key=lambda p: p.score, reverse=True)

    def get_active_symbols(self) -> List[str]:
        ranked = self.get_ranked_pairs()
        return [p.symbol for p in ranked if p.score >= self.min_score_activate]

    def _score_symbol(self, symbol: str, metrics) -> PairScore:
        base = float(getattr(metrics, "composite_score", 0.0))

        # lightweight, explainable components
        trend_bonus = min(8.0, max(0.0, float(getattr(metrics, "trend_strength", 0.0)) * 10.0))
        liquidity_bonus = min(6.0, max(0.0, float(getattr(metrics, "volume_24h", 0.0)) / 20.0))

        # costs and degradation penalties (explicit)
        spread_penalty = min(15.0, max(0.0, float(getattr(metrics, "spread_avg", 0.0)) * 40.0))
        vol_24h = float(getattr(metrics, "volatility_24h", 0.0))
        vol_7d = float(getattr(metrics, "volatility_7d", vol_24h))
        degradation_penalty = min(12.0, abs(vol_24h - vol_7d) * 2.0)

        final_score = max(0.0, min(100.0, base + trend_bonus + liquidity_bonus - spread_penalty - degradation_penalty))

        explain = {
            "base_composite": round(base, 4),
            "trend_bonus": round(trend_bonus, 4),
            "liquidity_bonus": round(liquidity_bonus, 4),
            "spread_penalty": round(spread_penalty, 4),
            "degradation_penalty": round(degradation_penalty, 4),
            "formula": "base+trend+liquidity-spread-degradation",
        }

        return PairScore(symbol=symbol, score=round(final_score, 4), explain=explain)
