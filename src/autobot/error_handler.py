"""
AUTOBOT Error Handler - Complete error management for 24/7 trading bot.

Handles:
- Network disconnections (retry with exponential backoff)
- API timeouts (configurable)
- Kraken API errors (specific error codes)
- Insufficient funds (pre-order balance check)
- Invalid price (level validation)
- Too many open orders (exchange limits)
- Rate limiting (429 errors)
- Unexpected crashes (logging + recovery)
"""

import time
import logging
import functools
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, Union

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

MAX_RETRIES: int = 3
RETRY_DELAYS: List[float] = [2.0, 4.0, 8.0]
CIRCUIT_BREAKER_THRESHOLD: int = 5
TIMEOUT_API: float = 30.0
MAX_OPEN_ORDERS_DEFAULT: int = 50
MIN_ORDER_SIZE: float = 0.0001
RATE_LIMIT_WINDOW: float = 60.0
RATE_LIMIT_MAX_CALLS: int = 15


class ErrorType(Enum):
    NETWORK = "network"
    TIMEOUT = "timeout"
    API_ERROR = "api_error"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    INVALID_PRICE = "invalid_price"
    INVALID_ORDER = "invalid_order"
    TOO_MANY_ORDERS = "too_many_orders"
    RATE_LIMITED = "rate_limited"
    AUTHENTICATION = "authentication"
    PERMISSION = "permission"
    UNKNOWN = "unknown"


class KrakenErrorCode(Enum):
    INVALID_ARGUMENTS = "EGeneral:Invalid arguments"
    PERMISSION_DENIED = "EAPI:Invalid key"
    INVALID_NONCE = "EAPI:Invalid nonce"
    RATE_LIMIT = "EAPI:Rate limit exceeded"
    ORDERS_RATE_LIMIT = "EOrder:Rate limit exceeded"
    INSUFFICIENT_FUNDS = "EOrder:Insufficient funds"
    INVALID_ORDER = "EOrder:Invalid order"
    ORDER_MINIMUM = "EOrder:Order minimum not met"
    UNKNOWN_ORDER = "EOrder:Unknown order"
    UNAVAILABLE = "EService:Unavailable"
    MARKET_SUSPENDED = "EService:Market in cancel_only mode"
    DEADLINE_ELAPSED = "EService:Deadline elapsed"
    UNKNOWN_ASSET_PAIR = "EGeneral:Unknown asset pair"
    INVALID_PRICE = "EOrder:Invalid price"
    TOO_MANY_ORDERS = "EOrder:Orders limit exceeded"


KRAKEN_ERROR_MAP: Dict[str, ErrorType] = {
    "EGeneral:Invalid arguments": ErrorType.INVALID_ORDER,
    "EAPI:Invalid key": ErrorType.AUTHENTICATION,
    "EAPI:Invalid nonce": ErrorType.AUTHENTICATION,
    "EAPI:Rate limit exceeded": ErrorType.RATE_LIMITED,
    "EOrder:Rate limit exceeded": ErrorType.RATE_LIMITED,
    "EOrder:Insufficient funds": ErrorType.INSUFFICIENT_FUNDS,
    "EOrder:Invalid order": ErrorType.INVALID_ORDER,
    "EOrder:Order minimum not met": ErrorType.INVALID_ORDER,
    "EOrder:Unknown order": ErrorType.INVALID_ORDER,
    "EService:Unavailable": ErrorType.NETWORK,
    "EService:Market in cancel_only mode": ErrorType.API_ERROR,
    "EService:Deadline elapsed": ErrorType.TIMEOUT,
    "EGeneral:Unknown asset pair": ErrorType.INVALID_ORDER,
    "EOrder:Invalid price": ErrorType.INVALID_PRICE,
    "EOrder:Orders limit exceeded": ErrorType.TOO_MANY_ORDERS,
}

RETRYABLE_ERRORS: set = {
    ErrorType.NETWORK,
    ErrorType.TIMEOUT,
    ErrorType.RATE_LIMITED,
}

NON_RETRYABLE_ERRORS: set = {
    ErrorType.INSUFFICIENT_FUNDS,
    ErrorType.INVALID_PRICE,
    ErrorType.INVALID_ORDER,
    ErrorType.AUTHENTICATION,
    ErrorType.PERMISSION,
}


class TradingError(Exception):
    def __init__(
        self,
        message: str,
        error_type: ErrorType = ErrorType.UNKNOWN,
        original_error: Optional[Exception] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.original_error = original_error
        self.details = details or {}
        self.timestamp = datetime.utcnow()


class InsufficientFundsError(TradingError):
    def __init__(
        self,
        message: str,
        required: float = 0.0,
        available: float = 0.0,
        original_error: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            error_type=ErrorType.INSUFFICIENT_FUNDS,
            original_error=original_error,
            details={"required": required, "available": available},
        )
        self.required = required
        self.available = available


class InvalidPriceError(TradingError):
    def __init__(
        self,
        message: str,
        price: float = 0.0,
        min_price: float = 0.0,
        max_price: float = 0.0,
        original_error: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            error_type=ErrorType.INVALID_PRICE,
            original_error=original_error,
            details={
                "price": price,
                "min_price": min_price,
                "max_price": max_price,
            },
        )


class RateLimitError(TradingError):
    def __init__(
        self,
        message: str,
        retry_after: float = 0.0,
        original_error: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            error_type=ErrorType.RATE_LIMITED,
            original_error=original_error,
            details={"retry_after": retry_after},
        )
        self.retry_after = retry_after


class CircuitBreakerOpenError(TradingError):
    def __init__(self, message: str, reset_time: Optional[datetime] = None):
        super().__init__(
            message,
            error_type=ErrorType.UNKNOWN,
            details={"reset_time": reset_time.isoformat() if reset_time else None},
        )
        self.reset_time = reset_time


class EmergencyStopError(TradingError):
    def __init__(self, message: str, reason: str = ""):
        super().__init__(
            message,
            error_type=ErrorType.UNKNOWN,
            details={"reason": reason},
        )
        self.reason = reason


@dataclass
class ErrorRecord:
    timestamp: datetime
    error_type: ErrorType
    message: str
    function_name: str
    retry_count: int = 0
    resolved: bool = False
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "error_type": self.error_type.value,
            "message": self.message,
            "function_name": self.function_name,
            "retry_count": self.retry_count,
            "resolved": self.resolved,
            "details": self.details,
        }


@dataclass
class CircuitBreakerState:
    failure_count: int = 0
    last_failure_time: Optional[datetime] = None
    is_open: bool = False
    open_since: Optional[datetime] = None
    reset_time: Optional[datetime] = None
    half_open_attempts: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "failure_count": self.failure_count,
            "last_failure_time": (
                self.last_failure_time.isoformat()
                if self.last_failure_time
                else None
            ),
            "is_open": self.is_open,
            "open_since": (
                self.open_since.isoformat() if self.open_since else None
            ),
            "reset_time": (
                self.reset_time.isoformat() if self.reset_time else None
            ),
            "half_open_attempts": self.half_open_attempts,
        }


class ErrorHandler:
    """
    Complete error handler for AUTOBOT 24/7 trading bot.

    Provides:
    - with_retry(): Decorator with exponential backoff
    - validate_order(): Pre-send order validation
    - handle_api_error(): Kraken-specific error handling
    - check_balance_sufficient(): Balance check before order
    - circuit_breaker(): Stop after N consecutive errors
    - emergency_stop(): Emergency shutdown
    """

    def __init__(
        self,
        max_retries: int = MAX_RETRIES,
        retry_delays: Optional[List[float]] = None,
        circuit_breaker_threshold: int = CIRCUIT_BREAKER_THRESHOLD,
        circuit_breaker_cooldown: float = 60.0,
        timeout_api: float = TIMEOUT_API,
        max_open_orders: int = MAX_OPEN_ORDERS_DEFAULT,
        rate_limit_window: float = RATE_LIMIT_WINDOW,
        rate_limit_max_calls: int = RATE_LIMIT_MAX_CALLS,
        on_emergency_stop: Optional[Callable[[], None]] = None,
    ):
        self.max_retries = max_retries
        self.retry_delays = retry_delays or list(RETRY_DELAYS)
        self.circuit_breaker_threshold = circuit_breaker_threshold
        self.circuit_breaker_cooldown = circuit_breaker_cooldown
        self.timeout_api = timeout_api
        self.max_open_orders = max_open_orders
        self.rate_limit_window = rate_limit_window
        self.rate_limit_max_calls = rate_limit_max_calls
        self.on_emergency_stop = on_emergency_stop

        self._lock = threading.RLock()
        self._error_history: List[ErrorRecord] = []
        self._circuit_breakers: Dict[str, CircuitBreakerState] = {}
        self._api_call_timestamps: List[float] = []
        self._emergency_stopped = False
        self._emergency_stop_reason: str = ""
        self._consecutive_errors: int = 0

        logger.info(
            "ErrorHandler initialized: max_retries=%d, cb_threshold=%d, timeout=%ds",
            max_retries,
            circuit_breaker_threshold,
            timeout_api,
        )

    @property
    def is_emergency_stopped(self) -> bool:
        return self._emergency_stopped

    def with_retry(
        self,
        max_retries: Optional[int] = None,
        retry_delays: Optional[List[float]] = None,
        retryable_exceptions: Optional[Tuple[type, ...]] = None,
    ) -> Callable[[F], F]:
        _max_retries = max_retries if max_retries is not None else self.max_retries
        _retry_delays = retry_delays or self.retry_delays
        _retryable = retryable_exceptions or (
            ConnectionError,
            TimeoutError,
            OSError,
            RateLimitError,
        )

        def decorator(func: F) -> F:
            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                if self._emergency_stopped:
                    raise EmergencyStopError(
                        f"Emergency stop active: {self._emergency_stop_reason}",
                        reason=self._emergency_stop_reason,
                    )

                last_exception: Optional[Exception] = None

                for attempt in range(_max_retries + 1):
                    try:
                        result = func(*args, **kwargs)
                        if attempt > 0:
                            logger.info(
                                "%s succeeded after %d retries",
                                func.__name__,
                                attempt,
                            )
                        with self._lock:
                            self._consecutive_errors = 0
                        return result
                    except _retryable as exc:
                        last_exception = exc
                        delay = _retry_delays[min(attempt, len(_retry_delays) - 1)]

                        logger.warning(
                            "%s attempt %d/%d failed: %s. Retrying in %.1fs",
                            func.__name__,
                            attempt + 1,
                            _max_retries + 1,
                            str(exc),
                            delay,
                        )

                        self._record_error(
                            error_type=self._classify_exception(exc),
                            message=str(exc),
                            function_name=func.__name__,
                            retry_count=attempt,
                            details={"delay": delay},
                        )

                        if attempt < _max_retries:
                            if isinstance(exc, RateLimitError) and exc.retry_after > 0:
                                time.sleep(exc.retry_after)
                            else:
                                time.sleep(delay)
                    except TradingError:
                        raise
                    except Exception as exc:
                        self._record_error(
                            error_type=self._classify_exception(exc),
                            message=str(exc),
                            function_name=func.__name__,
                            retry_count=attempt,
                        )
                        raise

                with self._lock:
                    self._consecutive_errors += 1
                    if self._consecutive_errors >= self.circuit_breaker_threshold:
                        self.emergency_stop(
                            f"Too many consecutive errors ({self._consecutive_errors})"
                        )

                if last_exception is not None:
                    raise last_exception
                raise RuntimeError(f"{func.__name__} failed after {_max_retries} retries")

            return wrapper  # type: ignore[return-value]

        return decorator

    def circuit_breaker(
        self,
        name: Optional[str] = None,
        threshold: Optional[int] = None,
        cooldown: Optional[float] = None,
    ) -> Callable[[F], F]:
        _threshold = threshold or self.circuit_breaker_threshold
        _cooldown = cooldown or self.circuit_breaker_cooldown

        def decorator(func: F) -> F:
            cb_name = name or func.__name__

            with self._lock:
                if cb_name not in self._circuit_breakers:
                    self._circuit_breakers[cb_name] = CircuitBreakerState()

            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                if self._emergency_stopped:
                    raise EmergencyStopError(
                        f"Emergency stop active: {self._emergency_stop_reason}",
                        reason=self._emergency_stop_reason,
                    )

                with self._lock:
                    state = self._circuit_breakers[cb_name]

                    if state.is_open:
                        now = datetime.utcnow()
                        if state.reset_time and now >= state.reset_time:
                            state.is_open = False
                            state.half_open_attempts = 0
                            logger.info("Circuit breaker '%s' entering half-open state", cb_name)
                        else:
                            raise CircuitBreakerOpenError(
                                f"Circuit breaker '{cb_name}' is open until {state.reset_time}",
                                reset_time=state.reset_time,
                            )

                try:
                    result = func(*args, **kwargs)
                    with self._lock:
                        state = self._circuit_breakers[cb_name]
                        state.failure_count = 0
                        state.half_open_attempts = 0
                    return result
                except Exception as exc:
                    with self._lock:
                        state = self._circuit_breakers[cb_name]
                        state.failure_count += 1
                        state.last_failure_time = datetime.utcnow()

                        if state.failure_count >= _threshold:
                            state.is_open = True
                            state.open_since = datetime.utcnow()
                            state.reset_time = datetime.utcnow() + timedelta(
                                seconds=_cooldown
                            )
                            logger.error(
                                "Circuit breaker '%s' OPEN after %d failures. Reset at %s",
                                cb_name,
                                state.failure_count,
                                state.reset_time.isoformat(),
                            )
                    raise

            return wrapper  # type: ignore[return-value]

        return decorator

    def validate_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        size: float,
        price: Optional[float] = None,
        available_balance: float = 0.0,
        current_open_orders: int = 0,
        min_order_size: float = MIN_ORDER_SIZE,
        max_price: Optional[float] = None,
        min_price: Optional[float] = None,
        tick_size: Optional[float] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        details: Dict[str, Any] = {
            "checks_passed": [],
            "checks_failed": [],
            "warnings": [],
        }

        if self._emergency_stopped:
            details["checks_failed"].append("emergency_stop_active")
            return False, f"Emergency stop active: {self._emergency_stop_reason}", details

        if not symbol or not isinstance(symbol, str):
            details["checks_failed"].append("invalid_symbol")
            return False, "Invalid symbol", details
        details["checks_passed"].append("symbol_valid")

        if side.lower() not in ("buy", "sell"):
            details["checks_failed"].append("invalid_side")
            return False, f"Invalid side: {side}. Must be 'buy' or 'sell'", details
        details["checks_passed"].append("side_valid")

        valid_order_types = ("market", "limit", "stop-loss", "take-profit", "stop-loss-limit", "take-profit-limit")
        if order_type.lower() not in valid_order_types:
            details["checks_failed"].append("invalid_order_type")
            return False, f"Invalid order type: {order_type}", details
        details["checks_passed"].append("order_type_valid")

        if size <= 0:
            details["checks_failed"].append("invalid_size_negative")
            return False, f"Order size must be positive, got {size}", details
        if size < min_order_size:
            details["checks_failed"].append("size_below_minimum")
            return False, f"Order size {size} below minimum {min_order_size}", details
        details["checks_passed"].append("size_valid")

        if price is not None:
            if price <= 0:
                details["checks_failed"].append("invalid_price_negative")
                return False, f"Price must be positive, got {price}", details

            if min_price is not None and price < min_price:
                details["checks_failed"].append("price_below_minimum")
                return False, f"Price {price} below minimum {min_price}", details

            if max_price is not None and price > max_price:
                details["checks_failed"].append("price_above_maximum")
                return False, f"Price {price} above maximum {max_price}", details

            if tick_size is not None and tick_size > 0:
                remainder = price % tick_size
                if remainder > tick_size * 0.001:
                    details["warnings"].append(
                        f"Price {price} not aligned with tick size {tick_size}"
                    )

            details["checks_passed"].append("price_valid")

        if order_type.lower() in ("limit", "stop-loss-limit", "take-profit-limit") and price is None:
            details["checks_failed"].append("missing_price_for_limit_order")
            return False, f"Price required for {order_type} order", details

        order_cost = size * (price if price else 0)
        if side.lower() == "buy" and price is not None:
            if order_cost > available_balance:
                details["checks_failed"].append("insufficient_funds")
                return (
                    False,
                    f"Insufficient funds: need {order_cost:.4f}, have {available_balance:.4f}",
                    details,
                )
            if order_cost > available_balance * 0.95:
                details["warnings"].append(
                    f"Order uses {order_cost / available_balance * 100:.1f}% of available balance"
                )
        details["checks_passed"].append("balance_check")

        if current_open_orders >= self.max_open_orders:
            details["checks_failed"].append("too_many_open_orders")
            return (
                False,
                f"Too many open orders: {current_open_orders}/{self.max_open_orders}",
                details,
            )
        details["checks_passed"].append("open_orders_limit")

        if not self._check_rate_limit():
            details["checks_failed"].append("rate_limited")
            return False, "Rate limit exceeded, please wait", details
        details["checks_passed"].append("rate_limit")

        return True, "Order validated", details

    def handle_api_error(
        self,
        error_messages: Union[List[str], str],
        context: str = "",
    ) -> Tuple[ErrorType, bool, str]:
        if isinstance(error_messages, str):
            error_messages = [error_messages]

        for error_msg in error_messages:
            error_msg_stripped = error_msg.strip()

            if error_msg_stripped in KRAKEN_ERROR_MAP:
                error_type = KRAKEN_ERROR_MAP[error_msg_stripped]
                is_retryable = error_type in RETRYABLE_ERRORS

                self._record_error(
                    error_type=error_type,
                    message=error_msg_stripped,
                    function_name=context or "handle_api_error",
                    details={"kraken_error": error_msg_stripped, "retryable": is_retryable},
                )

                logger.warning(
                    "Kraken API error [%s]: %s (retryable=%s)",
                    error_type.value,
                    error_msg_stripped,
                    is_retryable,
                )

                return error_type, is_retryable, self._get_recovery_hint(error_type, error_msg_stripped)

            for known_prefix, error_type in KRAKEN_ERROR_MAP.items():
                prefix = known_prefix.split(":")[0] + ":"
                if error_msg_stripped.startswith(prefix):
                    is_retryable = error_type in RETRYABLE_ERRORS

                    self._record_error(
                        error_type=error_type,
                        message=error_msg_stripped,
                        function_name=context or "handle_api_error",
                        details={"kraken_error": error_msg_stripped, "retryable": is_retryable},
                    )

                    return error_type, is_retryable, self._get_recovery_hint(error_type, error_msg_stripped)

        self._record_error(
            error_type=ErrorType.UNKNOWN,
            message=str(error_messages),
            function_name=context or "handle_api_error",
        )

        return ErrorType.UNKNOWN, False, "Unknown error, manual review required"

    def check_balance_sufficient(
        self,
        required_amount: float,
        available_balance: float,
        currency: str = "USD",
        include_fees: bool = True,
        fee_rate: float = 0.0026,
    ) -> Tuple[bool, Dict[str, float]]:
        total_required = required_amount
        fee_amount = 0.0

        if include_fees:
            fee_amount = required_amount * fee_rate
            total_required = required_amount + fee_amount

        margin = available_balance - total_required
        margin_pct = (margin / available_balance * 100) if available_balance > 0 else 0.0

        result = {
            "required_amount": required_amount,
            "fee_amount": fee_amount,
            "total_required": total_required,
            "available_balance": available_balance,
            "margin": margin,
            "margin_pct": margin_pct,
        }

        if total_required > available_balance:
            logger.warning(
                "Insufficient %s balance: need %.4f (incl. fees %.4f), have %.4f",
                currency,
                total_required,
                fee_amount,
                available_balance,
            )
            return False, result

        if margin_pct < 5.0:
            logger.warning(
                "Low %s balance margin: %.2f%% remaining after order",
                currency,
                margin_pct,
            )

        return True, result

    def emergency_stop(self, reason: str) -> None:
        with self._lock:
            if self._emergency_stopped:
                logger.warning("Emergency stop already active: %s", self._emergency_stop_reason)
                return

            self._emergency_stopped = True
            self._emergency_stop_reason = reason

        logger.critical("EMERGENCY STOP ACTIVATED: %s", reason)

        self._record_error(
            error_type=ErrorType.UNKNOWN,
            message=f"EMERGENCY STOP: {reason}",
            function_name="emergency_stop",
            details={"reason": reason, "timestamp": datetime.utcnow().isoformat()},
        )

        if self.on_emergency_stop is not None:
            try:
                self.on_emergency_stop()
            except Exception as callback_err:
                logger.error("Error in emergency stop callback: %s", callback_err)

    def reset_emergency_stop(self) -> None:
        with self._lock:
            self._emergency_stopped = False
            self._emergency_stop_reason = ""
            self._consecutive_errors = 0
        logger.info("Emergency stop reset")

    def reset_circuit_breaker(self, name: str) -> bool:
        with self._lock:
            if name in self._circuit_breakers:
                self._circuit_breakers[name] = CircuitBreakerState()
                logger.info("Circuit breaker '%s' reset", name)
                return True
        return False

    def get_circuit_breaker_state(self, name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            if name in self._circuit_breakers:
                return self._circuit_breakers[name].to_dict()
        return None

    def get_error_stats(self) -> Dict[str, Any]:
        with self._lock:
            total = len(self._error_history)
            by_type: Dict[str, int] = {}
            for record in self._error_history:
                key = record.error_type.value
                by_type[key] = by_type.get(key, 0) + 1

            resolved = sum(1 for r in self._error_history if r.resolved)
            recent = [r.to_dict() for r in self._error_history[-10:]]

            cb_states = {
                name: state.to_dict()
                for name, state in self._circuit_breakers.items()
            }

            return {
                "total_errors": total,
                "resolved_errors": resolved,
                "errors_by_type": by_type,
                "consecutive_errors": self._consecutive_errors,
                "emergency_stopped": self._emergency_stopped,
                "emergency_stop_reason": self._emergency_stop_reason,
                "circuit_breakers": cb_states,
                "recent_errors": recent,
            }

    def get_error_history(
        self, limit: int = 50, error_type: Optional[ErrorType] = None
    ) -> List[Dict[str, Any]]:
        with self._lock:
            filtered = self._error_history
            if error_type is not None:
                filtered = [r for r in filtered if r.error_type == error_type]
            return [r.to_dict() for r in filtered[-limit:]]

    def _record_error(
        self,
        error_type: ErrorType,
        message: str,
        function_name: str,
        retry_count: int = 0,
        resolved: bool = False,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        record = ErrorRecord(
            timestamp=datetime.utcnow(),
            error_type=error_type,
            message=message,
            function_name=function_name,
            retry_count=retry_count,
            resolved=resolved,
            details=details or {},
        )

        with self._lock:
            self._error_history.append(record)
            if len(self._error_history) > 1000:
                self._error_history = self._error_history[-500:]

    def _classify_exception(self, exc: Exception) -> ErrorType:
        if isinstance(exc, TradingError):
            return exc.error_type

        exc_type = type(exc).__name__.lower()
        exc_msg = str(exc).lower()

        if isinstance(exc, TimeoutError):
            return ErrorType.TIMEOUT
        if isinstance(exc, (ConnectionError, OSError)):
            return ErrorType.NETWORK
        if "timeout" in exc_msg or "timed out" in exc_msg:
            return ErrorType.TIMEOUT
        if "connection" in exc_msg or "network" in exc_msg or "unreachable" in exc_msg:
            return ErrorType.NETWORK
        if "429" in exc_msg or "rate limit" in exc_msg or "too many requests" in exc_msg:
            return ErrorType.RATE_LIMITED
        if "insufficient" in exc_msg or "balance" in exc_msg:
            return ErrorType.INSUFFICIENT_FUNDS
        if "permission" in exc_type or "forbidden" in exc_msg:
            return ErrorType.PERMISSION
        if "auth" in exc_type or "unauthorized" in exc_msg:
            return ErrorType.AUTHENTICATION

        return ErrorType.UNKNOWN

    def _check_rate_limit(self) -> bool:
        now = time.monotonic()
        with self._lock:
            self._api_call_timestamps = [
                t for t in self._api_call_timestamps if now - t < self.rate_limit_window
            ]
            if len(self._api_call_timestamps) >= self.rate_limit_max_calls:
                return False
            self._api_call_timestamps.append(now)
        return True

    def _get_recovery_hint(self, error_type: ErrorType, error_msg: str) -> str:
        hints: Dict[ErrorType, str] = {
            ErrorType.INSUFFICIENT_FUNDS: "Reduce order size or add funds",
            ErrorType.INVALID_PRICE: "Check price levels and tick size",
            ErrorType.INVALID_ORDER: "Verify order parameters (symbol, size, type)",
            ErrorType.RATE_LIMITED: "Wait before next API call (backoff recommended)",
            ErrorType.AUTHENTICATION: "Check API key and secret configuration",
            ErrorType.PERMISSION: "Verify API key permissions for this operation",
            ErrorType.NETWORK: "Check network connectivity, retry shortly",
            ErrorType.TIMEOUT: "API response slow, retry with increased timeout",
            ErrorType.TOO_MANY_ORDERS: "Cancel some open orders before placing new ones",
        }
        return hints.get(error_type, "Unknown error, check logs for details")


_default_handler: Optional[ErrorHandler] = None
_handler_lock = threading.Lock()


def get_error_handler(**kwargs: Any) -> ErrorHandler:
    global _default_handler
    with _handler_lock:
        if _default_handler is None:
            _default_handler = ErrorHandler(**kwargs)
        return _default_handler


def with_retry(
    max_retries: int = MAX_RETRIES,
    retry_delays: Optional[List[float]] = None,
) -> Callable[[F], F]:
    handler = get_error_handler()
    return handler.with_retry(max_retries=max_retries, retry_delays=retry_delays)


def circuit_breaker(
    name: Optional[str] = None,
    threshold: int = CIRCUIT_BREAKER_THRESHOLD,
    cooldown: float = 60.0,
) -> Callable[[F], F]:
    handler = get_error_handler()
    return handler.circuit_breaker(name=name, threshold=threshold, cooldown=cooldown)


def validate_order(
    symbol: str,
    side: str,
    order_type: str,
    size: float,
    price: Optional[float] = None,
    available_balance: float = 0.0,
    current_open_orders: int = 0,
    **kwargs: Any,
) -> Tuple[bool, str, Dict[str, Any]]:
    handler = get_error_handler()
    return handler.validate_order(
        symbol=symbol,
        side=side,
        order_type=order_type,
        size=size,
        price=price,
        available_balance=available_balance,
        current_open_orders=current_open_orders,
        **kwargs,
    )


def handle_api_error(
    error_messages: Union[List[str], str],
    context: str = "",
) -> Tuple[ErrorType, bool, str]:
    handler = get_error_handler()
    return handler.handle_api_error(error_messages=error_messages, context=context)


def check_balance_sufficient(
    required_amount: float,
    available_balance: float,
    currency: str = "USD",
    include_fees: bool = True,
    fee_rate: float = 0.0026,
) -> Tuple[bool, Dict[str, float]]:
    handler = get_error_handler()
    return handler.check_balance_sufficient(
        required_amount=required_amount,
        available_balance=available_balance,
        currency=currency,
        include_fees=include_fees,
        fee_rate=fee_rate,
    )


def emergency_stop(reason: str) -> None:
    handler = get_error_handler()
    handler.emergency_stop(reason=reason)
