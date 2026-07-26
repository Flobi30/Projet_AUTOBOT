"""A non-mutating executor used by the research/observation runtime.

It deliberately implements the small asynchronous executor surface consumed
by the active orchestrator while refusing every order mutation.  It performs
no network I/O, creates no paper database and holds no capital state.
"""

from __future__ import annotations

from typing import Any, Callable, Coroutine, Optional

from .order_executor import OrderResult, OrderSide, OrderStatus
from .order_executor_async import (
    OrderCollectionRecovery,
    OrderRecoveryLookup,
    OrderRecoveryLookupState,
)


OBSERVATION_EXECUTION_DISABLED = "observation_only_execution_disabled"


class ObservationOnlyOrderExecutor:
    """Fail-closed async executor with no fill, wallet or order side effects."""

    execution_enabled = False
    execution_mode = "observation_only"

    def __init__(self) -> None:
        self._circuit_breaker_callback: Optional[Callable[[], Coroutine[Any, Any, None]]] = None

    def set_circuit_breaker_callback(
        self,
        callback: Callable[[], Coroutine[Any, Any, None]],
    ) -> None:
        self._circuit_breaker_callback = callback

    async def execute_market_order(
        self,
        symbol: str,
        side: OrderSide,
        volume: float,
        **_kwargs: Any,
    ) -> OrderResult:
        return self._rejected_result(symbol, side, volume)

    async def execute_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        volume: float,
        _price: float,
        **_kwargs: Any,
    ) -> OrderResult:
        return self._rejected_result(symbol, side, volume)

    async def execute_stop_loss_order(
        self,
        symbol: str,
        volume: float,
        _stop_price: float,
        **_kwargs: Any,
    ) -> OrderResult:
        return self._rejected_result(symbol, OrderSide.SELL, volume)

    async def cancel_order(self, _txid: str) -> bool:
        return False

    async def cancel_all_orders(self, _userref: Optional[int] = None) -> bool:
        return False

    async def get_balance(self) -> dict[str, float]:
        return {}

    async def get_trade_balance(self, _asset: str = "EUR") -> dict[str, float]:
        return {}

    async def get_order_status(self, _txid: str) -> Optional[OrderStatus]:
        return None

    async def get_order_status_for_recovery(self, _txid: str) -> OrderRecoveryLookup:
        return OrderRecoveryLookup(
            state=OrderRecoveryLookupState.UNAVAILABLE,
            reason=OBSERVATION_EXECUTION_DISABLED,
        )

    async def get_open_orders(self) -> dict[str, dict[str, Any]]:
        return {}

    async def get_open_orders_for_recovery(self) -> OrderCollectionRecovery:
        return OrderCollectionRecovery(
            available=False,
            orders={},
            reason=OBSERVATION_EXECUTION_DISABLED,
        )

    async def get_closed_orders(self, **_kwargs: Any) -> dict[str, dict[str, Any]]:
        return {}

    async def close(self) -> None:
        return None

    @staticmethod
    def _rejected_result(symbol: str, side: OrderSide, volume: float) -> OrderResult:
        return OrderResult(
            success=False,
            error=OBSERVATION_EXECUTION_DISABLED,
            raw_response={
                "reason": OBSERVATION_EXECUTION_DISABLED,
                "symbol": str(symbol),
                "side": getattr(side, "value", str(side)),
                "requested_volume": float(volume),
            },
        )
