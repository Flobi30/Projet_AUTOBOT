from __future__ import annotations

from typing import Dict, Iterable


class RiskClusterManager:
    """Cluster-level risk caps to avoid concentrated correlated exposure."""

    def __init__(self, cluster_cap: float = 0.35):
        self.cluster_cap = max(0.05, min(0.95, float(cluster_cap)))

    def cluster_for_symbol(self, symbol: str) -> str:
        s = (symbol or "").upper()
        if "FOREX" in s or s.endswith("USD") and "/" in s and any(x in s for x in ("EUR", "GBP", "JPY")):
            return "FOREX"
        if "BTC" in s:
            return "BTC"
        if "ETH" in s:
            return "ETH"
        if any(x in s for x in ("SOL", "ADA", "DOT", "MATIC", "POL", "XRP", "AVAX", "LINK")):
            return "ALTS"
        return "OTHER"

    def exposure_by_cluster(self, instances: Iterable[object]) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for inst in instances:
            sym = str(getattr(getattr(inst, "config", None), "symbol", ""))
            cap = float(getattr(inst, "get_current_capital", lambda: 0.0)() or 0.0)
            c = self.cluster_for_symbol(sym)
            out[c] = out.get(c, 0.0) + max(0.0, cap)
        return out

    def allowed_multiplier(self, symbol: str, add_size: float, total_capital: float, exposures: Dict[str, float]) -> float:
        cluster = self.cluster_for_symbol(symbol)
        total_capital = max(1e-9, float(total_capital))
        current = float(exposures.get(cluster, 0.0))
        projected_ratio = (current + max(0.0, add_size)) / total_capital
        if projected_ratio <= self.cluster_cap:
            return 1.0
        overflow = projected_ratio - self.cluster_cap
        # linear penalty then floor
        penalty = max(0.1, 1.0 - (overflow / max(0.05, self.cluster_cap)))
        return min(1.0, penalty)
