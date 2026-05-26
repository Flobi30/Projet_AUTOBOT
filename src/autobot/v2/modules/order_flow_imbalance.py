"""Order-flow imbalance and lightweight order-book microstructure features."""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _clamp(value: float, minimum: float = -1.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, float(value)))


def _normalize_pair(pair: str) -> str:
    normalized = str(pair or "").upper().replace("/", "").replace("-", "").strip()
    aliases = {
        "XBTEUR": "XXBTZEUR",
        "BTCEUR": "XXBTZEUR",
        "ETHEUR": "XETHZEUR",
        "LTCEUR": "XLTCZEUR",
        "XRPEUR": "XXRPZEUR",
        "XLMEUR": "XXLMZEUR",
    }
    return aliases.get(normalized, normalized)


@dataclass(frozen=True)
class MicrostructureSnapshot:
    symbol: str
    has_book: bool
    bid: float = 0.0
    ask: float = 0.0
    mid: float = 0.0
    spread_bps: float = 0.0
    bid_depth_eur: float = 0.0
    ask_depth_eur: float = 0.0
    depth_imbalance: float = 0.0
    ofi_score: float = 0.0
    buy_adverse_selection_risk: float = 0.0
    sell_adverse_selection_risk: float = 0.0
    adverse_selection_risk: float = 0.0
    age_ms: float = 0.0
    reason: str = "ok"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OrderFlowImbalance:
    """Tracks L2 book pressure and exposes execution-quality features."""

    def __init__(self, depth: int = 10) -> None:
        self._depth = max(1, int(depth))
        self._books: Dict[str, Dict[str, Dict[float, float]]] = {}
        self._updated_at: Dict[str, float] = {}
        self._ofi_values: Dict[str, float] = {}
        self._ofi_history: Dict[str, List[float]] = {}

    async def on_book_update(self, pair: str, data: dict) -> None:
        """Kraken book callback. Supports snapshots (`as`/`bs`) and updates (`a`/`b`)."""
        key = _normalize_pair(pair)
        if key not in self._books:
            self._books[key] = {"bids": {}, "asks": {}}
            self._ofi_history[key] = []

        book = self._books[key]
        self._updated_at[key] = time.time()

        if "as" in data:
            book["asks"] = self._clean_side(data["as"])
        if "bs" in data:
            book["bids"] = self._clean_side(data["bs"])
            return

        ofi_delta = 0.0
        if "a" in data:
            old_best_ask = min(book["asks"].keys()) if book["asks"] else None
            old_best_ask_vol = book["asks"].get(old_best_ask, 0.0) if old_best_ask else 0.0

            for row in data["a"]:
                try:
                    price, volume = float(row[0]), float(row[1])
                except (TypeError, ValueError, IndexError):
                    continue
                if volume <= 0.0:
                    book["asks"].pop(price, None)
                else:
                    book["asks"][price] = volume

            new_best_ask = min(book["asks"].keys()) if book["asks"] else None
            new_best_ask_vol = book["asks"].get(new_best_ask, 0.0) if new_best_ask else 0.0
            if new_best_ask and old_best_ask:
                if new_best_ask > old_best_ask:
                    ofi_delta += old_best_ask_vol
                elif new_best_ask < old_best_ask:
                    ofi_delta -= new_best_ask_vol
                else:
                    ofi_delta += old_best_ask_vol - new_best_ask_vol

        if "b" in data:
            old_best_bid = max(book["bids"].keys()) if book["bids"] else None
            old_best_bid_vol = book["bids"].get(old_best_bid, 0.0) if old_best_bid else 0.0

            for row in data["b"]:
                try:
                    price, volume = float(row[0]), float(row[1])
                except (TypeError, ValueError, IndexError):
                    continue
                if volume <= 0.0:
                    book["bids"].pop(price, None)
                else:
                    book["bids"][price] = volume

            new_best_bid = max(book["bids"].keys()) if book["bids"] else None
            new_best_bid_vol = book["bids"].get(new_best_bid, 0.0) if new_best_bid else 0.0
            if new_best_bid and old_best_bid:
                if new_best_bid > old_best_bid:
                    ofi_delta += new_best_bid_vol
                elif new_best_bid < old_best_bid:
                    ofi_delta -= old_best_bid_vol
                else:
                    ofi_delta += new_best_bid_vol - old_best_bid_vol

        self._ofi_values[key] = self._ofi_values.get(key, 0.0) + ofi_delta
        self._ofi_history[key].append(ofi_delta)
        del self._ofi_history[key][:-100]

    def get_ofi_score(self, pair: str) -> float:
        """Return -1..1, where negative means sell pressure and positive buy pressure."""
        history = self._ofi_history.get(_normalize_pair(pair), [])
        if not history:
            return 0.0
        recent = history[-20:]
        recent_sum = sum(recent)
        scale = max(1.0, sum(abs(value) for value in recent) * 0.35)
        return _clamp(recent_sum / scale)

    def get_snapshot(self, pair: str) -> MicrostructureSnapshot:
        """Return a normalized snapshot used by paper realism and execution guards."""
        key = _normalize_pair(pair)
        book = self._books.get(key)
        if not book or not book.get("bids") or not book.get("asks"):
            return MicrostructureSnapshot(symbol=key, has_book=False, reason="book_unavailable")

        bids = sorted(book["bids"].items(), key=lambda item: item[0], reverse=True)[: self._depth]
        asks = sorted(book["asks"].items(), key=lambda item: item[0])[: self._depth]
        bid = float(bids[0][0]) if bids else 0.0
        ask = float(asks[0][0]) if asks else 0.0
        if bid <= 0.0 or ask <= 0.0 or bid >= ask:
            mid = (bid + ask) / 2.0 if bid > 0.0 and ask > 0.0 else 0.0
            return MicrostructureSnapshot(
                symbol=key,
                has_book=False,
                bid=bid,
                ask=ask,
                mid=mid,
                age_ms=max(0.0, (time.time() - self._updated_at.get(key, time.time())) * 1000.0),
                reason="invalid_book",
            )

        mid = (bid + ask) / 2.0
        spread_bps = ((ask - bid) / mid) * 10000.0
        bid_depth = sum(float(price) * float(volume) for price, volume in bids)
        ask_depth = sum(float(price) * float(volume) for price, volume in asks)
        depth_total = max(1e-9, bid_depth + ask_depth)
        depth_imbalance = _clamp((bid_depth - ask_depth) / depth_total)
        ofi_score = self.get_ofi_score(key)
        spread_risk = _clamp(spread_bps / 80.0, 0.0, 1.0)
        buy_risk = _clamp(
            (max(0.0, -depth_imbalance) * 0.45)
            + (max(0.0, -ofi_score) * 0.45)
            + (spread_risk * 0.10),
            0.0,
            1.0,
        )
        sell_risk = _clamp(
            (max(0.0, depth_imbalance) * 0.45)
            + (max(0.0, ofi_score) * 0.45)
            + (spread_risk * 0.10),
            0.0,
            1.0,
        )
        age_ms = max(0.0, (time.time() - self._updated_at.get(key, time.time())) * 1000.0)
        return MicrostructureSnapshot(
            symbol=key,
            has_book=True,
            bid=bid,
            ask=ask,
            mid=mid,
            spread_bps=spread_bps,
            bid_depth_eur=bid_depth,
            ask_depth_eur=ask_depth,
            depth_imbalance=depth_imbalance,
            ofi_score=ofi_score,
            buy_adverse_selection_risk=buy_risk,
            sell_adverse_selection_risk=sell_risk,
            adverse_selection_risk=max(buy_risk, sell_risk),
            age_ms=age_ms,
            reason="ok",
        )

    def is_unbalanced_against(self, pair: str, side: str) -> bool:
        snapshot = self.get_snapshot(pair)
        if not snapshot.has_book:
            return False
        score = self.get_ofi_score(pair)
        if side == "buy" and score < -0.6:
            return True
        if side == "sell" and score > 0.6:
            return True
        return False

    def get_quality_snapshot(self, pair: str) -> dict[str, Any]:
        """Return book diagnostics without implying tradability."""
        snapshot = self.get_snapshot(pair).to_dict()
        history = self._ofi_history.get(_normalize_pair(pair), [])
        snapshot["ofi_samples"] = len(history)
        return snapshot

    @staticmethod
    def _clean_side(rows: List[Any]) -> Dict[float, float]:
        clean: Dict[float, float] = {}
        for row in rows:
            try:
                price = float(row[0])
                volume = float(row[1])
            except (TypeError, ValueError, IndexError):
                continue
            if price <= 0.0:
                continue
            if volume <= 0.0:
                clean.pop(price, None)
            else:
                clean[price] = volume
        return clean
