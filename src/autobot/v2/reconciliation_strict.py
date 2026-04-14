from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class DivergenceItem:
    category: str
    severity: str
    message: str


class StrictReconciliation:
    """Strict local vs exchange reconciliation checks with kill criteria."""

    def __init__(self, cash_abs_threshold: float = 10.0, cash_rel_threshold: float = 0.005):
        self.cash_abs_threshold = cash_abs_threshold
        self.cash_rel_threshold = cash_rel_threshold

    def compare_balances(self, local_total: float, exchange_total: float) -> List[DivergenceItem]:
        divergences: List[DivergenceItem] = []
        drift = abs(local_total - exchange_total)
        rel = drift / exchange_total if exchange_total > 0 else 0.0
        if drift > self.cash_abs_threshold and rel > self.cash_rel_threshold:
            divergences.append(
                DivergenceItem(
                    category="balances",
                    severity="critical",
                    message=f"balance drift local={local_total:.2f} exchange={exchange_total:.2f}",
                )
            )
        return divergences

    def compare_open_orders(self, local_orders: Dict[str, Any], exchange_open_ids: set[str]) -> List[DivergenceItem]:
        divergences: List[DivergenceItem] = []
        for oid, order in local_orders.items():
            if order.get("status") in ("ACK", "PARTIAL", "SENT"):
                exid = order.get("exchange_order_id")
                if exid and exid not in exchange_open_ids:
                    divergences.append(
                        DivergenceItem(
                            category="open_orders",
                            severity="critical",
                            message=f"order {oid}/{exid} missing on exchange open orders",
                        )
                    )
        return divergences

    def compare_positions(self, local_positions: List[Dict[str, Any]], exchange_positions: List[Dict[str, Any]]) -> List[DivergenceItem]:
        divergences: List[DivergenceItem] = []
        local_count = len([p for p in local_positions if p.get("status") == "open"])
        exchange_count = len(exchange_positions)
        if local_count != exchange_count:
            divergences.append(
                DivergenceItem(
                    category="positions",
                    severity="critical",
                    message=f"position mismatch local={local_count} exchange={exchange_count}",
                )
            )
        return divergences

    def should_kill_switch(self, divergences: List[DivergenceItem]) -> bool:
        return any(d.severity == "critical" for d in divergences)

    def compare_fills_fees_pnl(
        self,
        local: Dict[str, float],
        exchange: Dict[str, float],
        pnl_abs_threshold: float = 5.0,
        fee_abs_threshold: float = 1.0,
    ) -> List[DivergenceItem]:
        """
        Compare local vs exchange aggregates:
        - realized_pnl
        - unrealized_pnl
        - fees
        """
        divergences: List[DivergenceItem] = []
        realized_diff = abs(local.get("realized_pnl", 0.0) - exchange.get("realized_pnl", 0.0))
        unrealized_diff = abs(local.get("unrealized_pnl", 0.0) - exchange.get("unrealized_pnl", 0.0))
        fees_diff = abs(local.get("fees", 0.0) - exchange.get("fees", 0.0))

        if realized_diff > pnl_abs_threshold:
            divergences.append(
                DivergenceItem(
                    category="realized_pnl",
                    severity="critical",
                    message=f"realized pnl mismatch diff={realized_diff:.2f}",
                )
            )
        if unrealized_diff > pnl_abs_threshold:
            divergences.append(
                DivergenceItem(
                    category="unrealized_pnl",
                    severity="warning",
                    message=f"unrealized pnl mismatch diff={unrealized_diff:.2f}",
                )
            )
        if fees_diff > fee_abs_threshold:
            divergences.append(
                DivergenceItem(
                    category="fees",
                    severity="critical",
                    message=f"fees mismatch diff={fees_diff:.2f}",
                )
            )
        return divergences

    def compare_trade_history_consistency(
        self,
        local_trade_ids: set[str],
        exchange_trade_ids: set[str],
    ) -> List[DivergenceItem]:
        divergences: List[DivergenceItem] = []
        missing_local = exchange_trade_ids - local_trade_ids
        missing_exchange = local_trade_ids - exchange_trade_ids
        if missing_local:
            divergences.append(
                DivergenceItem(
                    category="trade_history",
                    severity="critical",
                    message=f"{len(missing_local)} exchange trades missing locally",
                )
            )
        if missing_exchange:
            divergences.append(
                DivergenceItem(
                    category="trade_history",
                    severity="warning",
                    message=f"{len(missing_exchange)} local trades missing on exchange snapshot",
                )
            )
        return divergences
