"""
Tests for AUTOBOT error_handler module.

Covers:
- with_retry() decorator with exponential backoff
- validate_order() pre-send validation
- handle_api_error() Kraken-specific error handling
- check_balance_sufficient() balance verification
- circuit_breaker() decorator
- emergency_stop() shutdown
- Error classification and recovery hints
"""

import sys
import os
import time
import threading
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

root = os.path.dirname(os.path.dirname(__file__))
src = os.path.join(root, "src")
if src not in sys.path:
    sys.path.insert(0, src)

from autobot.error_handler import (
    CIRCUIT_BREAKER_THRESHOLD,
    MAX_RETRIES,
    RETRY_DELAYS,
    CircuitBreakerOpenError,
    CircuitBreakerState,
    EmergencyStopError,
    ErrorHandler,
    ErrorRecord,
    ErrorType,
    InsufficientFundsError,
    InvalidPriceError,
    KrakenErrorCode,
    KRAKEN_ERROR_MAP,
    RateLimitError,
    TradingError,
    check_balance_sufficient,
    handle_api_error,
    validate_order,
)


class TestConstants:
    def test_max_retries(self):
        assert MAX_RETRIES == 3

    def test_retry_delays(self):
        assert RETRY_DELAYS == [2.0, 4.0, 8.0]

    def test_circuit_breaker_threshold(self):
        assert CIRCUIT_BREAKER_THRESHOLD == 5


class TestCustomExceptions:
    def test_trading_error(self):
        err = TradingError("test error", ErrorType.NETWORK)
        assert str(err) == "test error"
        assert err.error_type == ErrorType.NETWORK
        assert isinstance(err.timestamp, datetime)

    def test_insufficient_funds_error(self):
        err = InsufficientFundsError("no funds", required=100.0, available=50.0)
        assert err.error_type == ErrorType.INSUFFICIENT_FUNDS
        assert err.required == 100.0
        assert err.available == 50.0
        assert err.details["required"] == 100.0

    def test_invalid_price_error(self):
        err = InvalidPriceError("bad price", price=10.0, min_price=20.0, max_price=30.0)
        assert err.error_type == ErrorType.INVALID_PRICE
        assert err.details["price"] == 10.0

    def test_rate_limit_error(self):
        err = RateLimitError("rate limited", retry_after=5.0)
        assert err.error_type == ErrorType.RATE_LIMITED
        assert err.retry_after == 5.0

    def test_circuit_breaker_open_error(self):
        reset = datetime.utcnow() + timedelta(minutes=1)
        err = CircuitBreakerOpenError("cb open", reset_time=reset)
        assert err.reset_time == reset

    def test_emergency_stop_error(self):
        err = EmergencyStopError("stop!", reason="too many losses")
        assert err.reason == "too many losses"


class TestErrorRecord:
    def test_to_dict(self):
        record = ErrorRecord(
            timestamp=datetime(2026, 1, 1, 12, 0, 0),
            error_type=ErrorType.NETWORK,
            message="connection lost",
            function_name="test_func",
            retry_count=2,
            resolved=True,
            details={"key": "value"},
        )
        d = record.to_dict()
        assert d["error_type"] == "network"
        assert d["message"] == "connection lost"
        assert d["retry_count"] == 2
        assert d["resolved"] is True


class TestCircuitBreakerState:
    def test_to_dict(self):
        state = CircuitBreakerState(failure_count=3, is_open=True)
        d = state.to_dict()
        assert d["failure_count"] == 3
        assert d["is_open"] is True


class TestWithRetry:
    def test_success_no_retry(self):
        handler = ErrorHandler(max_retries=3, retry_delays=[0.01, 0.01, 0.01])
        call_count = 0

        @handler.with_retry()
        def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = succeed()
        assert result == "ok"
        assert call_count == 1

    def test_retry_then_success(self):
        handler = ErrorHandler(max_retries=3, retry_delays=[0.01, 0.01, 0.01])
        call_count = 0

        @handler.with_retry()
        def fail_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("disconnected")
            return "recovered"

        result = fail_twice()
        assert result == "recovered"
        assert call_count == 3

    def test_all_retries_exhausted(self):
        handler = ErrorHandler(max_retries=2, retry_delays=[0.01, 0.01])

        @handler.with_retry()
        def always_fail():
            raise ConnectionError("always down")

        with pytest.raises(ConnectionError, match="always down"):
            always_fail()

    def test_non_retryable_exception_not_retried(self):
        handler = ErrorHandler(max_retries=3, retry_delays=[0.01, 0.01, 0.01])
        call_count = 0

        @handler.with_retry()
        def bad_order():
            nonlocal call_count
            call_count += 1
            raise TradingError("invalid order", ErrorType.INVALID_ORDER)

        with pytest.raises(TradingError):
            bad_order()
        assert call_count == 1

    def test_emergency_stop_blocks_retry(self):
        handler = ErrorHandler(max_retries=3, retry_delays=[0.01, 0.01, 0.01])
        handler.emergency_stop("test stop")

        @handler.with_retry()
        def do_something():
            return "ok"

        with pytest.raises(EmergencyStopError):
            do_something()

    def test_rate_limit_error_uses_retry_after(self):
        handler = ErrorHandler(max_retries=2, retry_delays=[0.01, 0.01])
        call_count = 0

        @handler.with_retry()
        def rate_limited_call():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RateLimitError("rate limited", retry_after=0.01)
            return "ok"

        result = rate_limited_call()
        assert result == "ok"
        assert call_count == 2


class TestCircuitBreaker:
    def test_circuit_breaker_opens_after_threshold(self):
        handler = ErrorHandler(
            circuit_breaker_threshold=3,
            circuit_breaker_cooldown=60.0,
        )

        @handler.circuit_breaker(name="test_cb", threshold=3, cooldown=60.0)
        def failing_func():
            raise ValueError("fail")

        for _ in range(3):
            with pytest.raises(ValueError):
                failing_func()

        with pytest.raises(CircuitBreakerOpenError):
            failing_func()

    def test_circuit_breaker_resets_on_success(self):
        handler = ErrorHandler(circuit_breaker_threshold=3)
        call_count = 0

        @handler.circuit_breaker(name="test_reset", threshold=3)
        def sometimes_fail():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise ValueError("fail")
            return "ok"

        for _ in range(2):
            with pytest.raises(ValueError):
                sometimes_fail()

        result = sometimes_fail()
        assert result == "ok"

        state = handler.get_circuit_breaker_state("test_reset")
        assert state is not None
        assert state["failure_count"] == 0

    def test_circuit_breaker_half_open_after_cooldown(self):
        handler = ErrorHandler(circuit_breaker_threshold=2, circuit_breaker_cooldown=0.1)

        @handler.circuit_breaker(name="test_half_open", threshold=2, cooldown=0.1)
        def failing_then_ok():
            return "ok"

        with handler._lock:
            handler._circuit_breakers["test_half_open"] = CircuitBreakerState(
                failure_count=2,
                is_open=True,
                open_since=datetime.utcnow() - timedelta(seconds=1),
                reset_time=datetime.utcnow() - timedelta(seconds=0.5),
            )

        result = failing_then_ok()
        assert result == "ok"

    def test_reset_circuit_breaker(self):
        handler = ErrorHandler()

        @handler.circuit_breaker(name="test_manual_reset", threshold=2)
        def dummy():
            raise ValueError("fail")

        for _ in range(2):
            with pytest.raises(ValueError):
                dummy()

        with pytest.raises(CircuitBreakerOpenError):
            dummy()

        handler.reset_circuit_breaker("test_manual_reset")
        state = handler.get_circuit_breaker_state("test_manual_reset")
        assert state["failure_count"] == 0
        assert state["is_open"] is False

    def test_circuit_breaker_emergency_stop(self):
        handler = ErrorHandler()
        handler.emergency_stop("test")

        @handler.circuit_breaker(name="test_estop")
        def do_something():
            return "ok"

        with pytest.raises(EmergencyStopError):
            do_something()


class TestValidateOrder:
    def setup_method(self):
        self.handler = ErrorHandler(
            max_open_orders=50,
            rate_limit_max_calls=1000,
        )

    def test_valid_market_buy(self):
        ok, msg, details = self.handler.validate_order(
            symbol="XBTUSD",
            side="buy",
            order_type="market",
            size=0.01,
            available_balance=10000.0,
            current_open_orders=0,
        )
        assert ok is True
        assert "validated" in msg.lower()

    def test_valid_limit_sell(self):
        ok, msg, details = self.handler.validate_order(
            symbol="ETHUSD",
            side="sell",
            order_type="limit",
            size=1.0,
            price=2000.0,
            available_balance=5000.0,
            current_open_orders=5,
        )
        assert ok is True

    def test_invalid_symbol(self):
        ok, msg, details = self.handler.validate_order(
            symbol="",
            side="buy",
            order_type="market",
            size=1.0,
        )
        assert ok is False
        assert "invalid_symbol" in details["checks_failed"]

    def test_invalid_side(self):
        ok, msg, details = self.handler.validate_order(
            symbol="XBTUSD",
            side="invalid",
            order_type="market",
            size=1.0,
        )
        assert ok is False
        assert "invalid_side" in details["checks_failed"]

    def test_invalid_order_type(self):
        ok, msg, details = self.handler.validate_order(
            symbol="XBTUSD",
            side="buy",
            order_type="foobar",
            size=1.0,
        )
        assert ok is False
        assert "invalid_order_type" in details["checks_failed"]

    def test_negative_size(self):
        ok, msg, details = self.handler.validate_order(
            symbol="XBTUSD",
            side="buy",
            order_type="market",
            size=-1.0,
        )
        assert ok is False
        assert "invalid_size_negative" in details["checks_failed"]

    def test_size_below_minimum(self):
        ok, msg, details = self.handler.validate_order(
            symbol="XBTUSD",
            side="buy",
            order_type="market",
            size=0.00001,
            min_order_size=0.001,
        )
        assert ok is False
        assert "size_below_minimum" in details["checks_failed"]

    def test_negative_price(self):
        ok, msg, details = self.handler.validate_order(
            symbol="XBTUSD",
            side="buy",
            order_type="limit",
            size=1.0,
            price=-100.0,
        )
        assert ok is False
        assert "invalid_price_negative" in details["checks_failed"]

    def test_price_below_minimum(self):
        ok, msg, details = self.handler.validate_order(
            symbol="XBTUSD",
            side="buy",
            order_type="limit",
            size=1.0,
            price=5.0,
            min_price=10.0,
        )
        assert ok is False
        assert "price_below_minimum" in details["checks_failed"]

    def test_price_above_maximum(self):
        ok, msg, details = self.handler.validate_order(
            symbol="XBTUSD",
            side="buy",
            order_type="limit",
            size=1.0,
            price=200.0,
            max_price=100.0,
        )
        assert ok is False
        assert "price_above_maximum" in details["checks_failed"]

    def test_limit_order_missing_price(self):
        ok, msg, details = self.handler.validate_order(
            symbol="XBTUSD",
            side="buy",
            order_type="limit",
            size=1.0,
            price=None,
        )
        assert ok is False
        assert "missing_price_for_limit_order" in details["checks_failed"]

    def test_insufficient_funds(self):
        ok, msg, details = self.handler.validate_order(
            symbol="XBTUSD",
            side="buy",
            order_type="limit",
            size=1.0,
            price=50000.0,
            available_balance=1000.0,
        )
        assert ok is False
        assert "insufficient_funds" in details["checks_failed"]

    def test_too_many_open_orders(self):
        ok, msg, details = self.handler.validate_order(
            symbol="XBTUSD",
            side="buy",
            order_type="market",
            size=0.01,
            available_balance=10000.0,
            current_open_orders=50,
        )
        assert ok is False
        assert "too_many_open_orders" in details["checks_failed"]

    def test_emergency_stop_blocks_validation(self):
        self.handler.emergency_stop("test")
        ok, msg, details = self.handler.validate_order(
            symbol="XBTUSD",
            side="buy",
            order_type="market",
            size=0.01,
        )
        assert ok is False
        assert "emergency_stop_active" in details["checks_failed"]

    def test_tick_size_warning(self):
        ok, msg, details = self.handler.validate_order(
            symbol="XBTUSD",
            side="buy",
            order_type="limit",
            size=0.01,
            price=50000.3,
            available_balance=100000.0,
            tick_size=0.5,
        )
        assert ok is True
        assert any("tick size" in w for w in details["warnings"])

    def test_high_balance_usage_warning(self):
        ok, msg, details = self.handler.validate_order(
            symbol="XBTUSD",
            side="buy",
            order_type="limit",
            size=0.96,
            price=1000.0,
            available_balance=1000.0,
        )
        assert ok is True
        assert any("balance" in w.lower() for w in details["warnings"])


class TestHandleApiError:
    def setup_method(self):
        self.handler = ErrorHandler()

    def test_insufficient_funds_error(self):
        error_type, retryable, hint = self.handler.handle_api_error(
            "EOrder:Insufficient funds"
        )
        assert error_type == ErrorType.INSUFFICIENT_FUNDS
        assert retryable is False
        assert "funds" in hint.lower()

    def test_rate_limit_error(self):
        error_type, retryable, hint = self.handler.handle_api_error(
            "EAPI:Rate limit exceeded"
        )
        assert error_type == ErrorType.RATE_LIMITED
        assert retryable is True

    def test_invalid_price_error(self):
        error_type, retryable, hint = self.handler.handle_api_error(
            "EOrder:Invalid price"
        )
        assert error_type == ErrorType.INVALID_PRICE
        assert retryable is False

    def test_too_many_orders(self):
        error_type, retryable, hint = self.handler.handle_api_error(
            "EOrder:Orders limit exceeded"
        )
        assert error_type == ErrorType.TOO_MANY_ORDERS
        assert retryable is False

    def test_authentication_error(self):
        error_type, retryable, hint = self.handler.handle_api_error(
            "EAPI:Invalid key"
        )
        assert error_type == ErrorType.AUTHENTICATION
        assert retryable is False

    def test_service_unavailable(self):
        error_type, retryable, hint = self.handler.handle_api_error(
            "EService:Unavailable"
        )
        assert error_type == ErrorType.NETWORK
        assert retryable is True

    def test_unknown_error(self):
        error_type, retryable, hint = self.handler.handle_api_error(
            "ESomething:totally_new"
        )
        assert error_type == ErrorType.UNKNOWN
        assert retryable is False

    def test_list_of_errors(self):
        error_type, retryable, hint = self.handler.handle_api_error(
            ["EOrder:Insufficient funds", "EGeneral:Invalid arguments"]
        )
        assert error_type == ErrorType.INSUFFICIENT_FUNDS

    def test_deadline_elapsed(self):
        error_type, retryable, hint = self.handler.handle_api_error(
            "EService:Deadline elapsed"
        )
        assert error_type == ErrorType.TIMEOUT
        assert retryable is True

    def test_market_suspended(self):
        error_type, retryable, hint = self.handler.handle_api_error(
            "EService:Market in cancel_only mode"
        )
        assert error_type == ErrorType.API_ERROR
        assert retryable is False

    def test_prefix_matching(self):
        error_type, retryable, hint = self.handler.handle_api_error(
            "EOrder:Some new order error"
        )
        assert error_type != ErrorType.UNKNOWN


class TestCheckBalanceSufficient:
    def setup_method(self):
        self.handler = ErrorHandler()

    def test_sufficient_balance(self):
        ok, result = self.handler.check_balance_sufficient(
            required_amount=100.0,
            available_balance=1000.0,
        )
        assert ok is True
        assert result["margin"] > 0
        assert result["total_required"] > 100.0

    def test_insufficient_balance(self):
        ok, result = self.handler.check_balance_sufficient(
            required_amount=1000.0,
            available_balance=100.0,
        )
        assert ok is False
        assert result["margin"] < 0

    def test_with_fees(self):
        ok, result = self.handler.check_balance_sufficient(
            required_amount=100.0,
            available_balance=100.0,
            fee_rate=0.01,
        )
        assert ok is False
        assert result["fee_amount"] == pytest.approx(1.0)
        assert result["total_required"] == pytest.approx(101.0)

    def test_without_fees(self):
        ok, result = self.handler.check_balance_sufficient(
            required_amount=100.0,
            available_balance=100.0,
            include_fees=False,
        )
        assert ok is True
        assert result["fee_amount"] == 0.0

    def test_zero_balance(self):
        ok, result = self.handler.check_balance_sufficient(
            required_amount=10.0,
            available_balance=0.0,
        )
        assert ok is False
        assert result["margin_pct"] == 0.0

    def test_low_margin_warning(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING):
            ok, result = self.handler.check_balance_sufficient(
                required_amount=96.0,
                available_balance=100.0,
                include_fees=False,
            )
        assert ok is True
        assert result["margin_pct"] < 5.0


class TestEmergencyStop:
    def test_emergency_stop_activates(self):
        handler = ErrorHandler()
        handler.emergency_stop("critical loss")
        assert handler.is_emergency_stopped is True

    def test_emergency_stop_with_callback(self):
        callback = MagicMock()
        handler = ErrorHandler(on_emergency_stop=callback)
        handler.emergency_stop("test")
        callback.assert_called_once()

    def test_emergency_stop_callback_error_handled(self):
        def bad_callback():
            raise RuntimeError("callback crash")

        handler = ErrorHandler(on_emergency_stop=bad_callback)
        handler.emergency_stop("test")
        assert handler.is_emergency_stopped is True

    def test_reset_emergency_stop(self):
        handler = ErrorHandler()
        handler.emergency_stop("test")
        assert handler.is_emergency_stopped is True
        handler.reset_emergency_stop()
        assert handler.is_emergency_stopped is False

    def test_double_emergency_stop(self):
        handler = ErrorHandler()
        handler.emergency_stop("first")
        handler.emergency_stop("second")
        assert handler._emergency_stop_reason == "first"

    def test_consecutive_errors_trigger_emergency(self):
        handler = ErrorHandler(
            max_retries=0,
            retry_delays=[0.01],
            circuit_breaker_threshold=3,
        )

        @handler.with_retry(max_retries=0, retry_delays=[0.01])
        def fail():
            raise ConnectionError("down")

        for _ in range(3):
            try:
                fail()
            except (ConnectionError, EmergencyStopError):
                pass

        assert handler.is_emergency_stopped is True


class TestErrorStats:
    def test_get_error_stats(self):
        handler = ErrorHandler()
        handler._record_error(
            error_type=ErrorType.NETWORK,
            message="test",
            function_name="test_func",
        )
        stats = handler.get_error_stats()
        assert stats["total_errors"] == 1
        assert stats["errors_by_type"]["network"] == 1

    def test_get_error_history(self):
        handler = ErrorHandler()
        handler._record_error(
            error_type=ErrorType.NETWORK,
            message="net error",
            function_name="func1",
        )
        handler._record_error(
            error_type=ErrorType.TIMEOUT,
            message="timeout",
            function_name="func2",
        )

        all_errors = handler.get_error_history()
        assert len(all_errors) == 2

        net_errors = handler.get_error_history(error_type=ErrorType.NETWORK)
        assert len(net_errors) == 1

    def test_error_history_pruning(self):
        handler = ErrorHandler()
        for i in range(1100):
            handler._record_error(
                error_type=ErrorType.NETWORK,
                message=f"error {i}",
                function_name="test",
            )
        assert len(handler._error_history) <= 1000


class TestClassifyException:
    def setup_method(self):
        self.handler = ErrorHandler()

    def test_connection_error(self):
        assert self.handler._classify_exception(ConnectionError("fail")) == ErrorType.NETWORK

    def test_timeout_error(self):
        assert self.handler._classify_exception(TimeoutError("slow")) == ErrorType.TIMEOUT

    def test_os_error(self):
        assert self.handler._classify_exception(OSError("io fail")) == ErrorType.NETWORK

    def test_trading_error(self):
        err = TradingError("test", ErrorType.INSUFFICIENT_FUNDS)
        assert self.handler._classify_exception(err) == ErrorType.INSUFFICIENT_FUNDS

    def test_rate_limit_from_message(self):
        err = Exception("HTTP 429 Too Many Requests")
        assert self.handler._classify_exception(err) == ErrorType.RATE_LIMITED

    def test_unknown_error(self):
        assert self.handler._classify_exception(ValueError("bad")) == ErrorType.UNKNOWN


class TestModuleLevelFunctions:
    def test_validate_order_module_func(self):
        ok, msg, details = validate_order(
            symbol="XBTUSD",
            side="buy",
            order_type="market",
            size=0.01,
            available_balance=10000.0,
        )
        assert ok is True

    def test_handle_api_error_module_func(self):
        error_type, retryable, hint = handle_api_error("EOrder:Insufficient funds")
        assert error_type == ErrorType.INSUFFICIENT_FUNDS

    def test_check_balance_module_func(self):
        ok, result = check_balance_sufficient(
            required_amount=10.0,
            available_balance=100.0,
        )
        assert ok is True


class TestKrakenErrorCodes:
    def test_all_error_codes_mapped(self):
        for code in KrakenErrorCode:
            assert code.value in KRAKEN_ERROR_MAP

    def test_error_map_returns_valid_types(self):
        for error_msg, error_type in KRAKEN_ERROR_MAP.items():
            assert isinstance(error_type, ErrorType)
