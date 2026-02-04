"""
Tests for data_connector exceptions module.
"""

import pytest
from src.data_connector.exceptions import (
    DataConnectorError,
    ConnectionError,
    ReconnectionError,
    IBError,
    RateLimitExceeded,
    CircuitBreakerOpen,
    HeartbeatTimeout,
)


class TestDataConnectorError:
    """Tests for base DataConnectorError."""
    
    def test_basic_error(self):
        """Test basic error creation."""
        error = DataConnectorError("Test error")
        assert str(error) == "Test error"
        assert error.message == "Test error"
        assert error.error_code is None
        assert error.details == {}
    
    def test_error_with_code(self):
        """Test error with error code."""
        error = DataConnectorError("Test error", error_code=500)
        assert error.error_code == 500
    
    def test_error_with_details(self):
        """Test error with details."""
        details = {"key": "value", "count": 42}
        error = DataConnectorError("Test error", details=details)
        assert error.details == details
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        error = DataConnectorError(
            "Test error",
            error_code=500,
            details={"extra": "info"}
        )
        result = error.to_dict()
        
        assert result["error_type"] == "DataConnectorError"
        assert result["message"] == "Test error"
        assert result["error_code"] == 500
        assert result["details"]["extra"] == "info"


class TestConnectionError:
    """Tests for ConnectionError."""
    
    def test_connection_error(self):
        """Test connection error creation."""
        error = ConnectionError("Failed to connect")
        assert isinstance(error, DataConnectorError)
        assert error.message == "Failed to connect"


class TestReconnectionError:
    """Tests for ReconnectionError."""
    
    def test_reconnection_error(self):
        """Test reconnection error with attempts."""
        error = ReconnectionError(
            "Reconnection failed",
            attempts=5
        )
        assert error.attempts == 5
        assert error.details["attempts"] == 5
    
    def test_reconnection_error_with_last_error(self):
        """Test reconnection error with last error."""
        original = ValueError("Original error")
        error = ReconnectionError(
            "Reconnection failed",
            attempts=3,
            last_error=original
        )
        assert error.last_error == original
        assert "Original error" in error.details["last_error"]


class TestIBError:
    """Tests for IBError."""
    
    def test_ib_error_basic(self):
        """Test basic IB error."""
        error = IBError(
            "Connection lost",
            ib_error_code=1100
        )
        assert error.ib_error_code == 1100
        assert error.error_code == 1100
        assert "Connectivity between IB and TWS has been lost" in error.details["ib_error_description"]
    
    def test_ib_error_with_req_id(self):
        """Test IB error with request ID."""
        error = IBError(
            "Request failed",
            ib_error_code=502,
            req_id=12345
        )
        assert error.req_id == 12345
        assert error.details["req_id"] == 12345
    
    def test_is_recoverable(self):
        """Test recoverable error detection."""
        recoverable = IBError("Lost", ib_error_code=1100)
        assert recoverable.is_recoverable is True
        
        not_recoverable = IBError("Fatal", ib_error_code=502)
        assert not_recoverable.is_recoverable is False
    
    def test_is_fatal(self):
        """Test fatal error detection."""
        fatal = IBError("Fatal", ib_error_code=502)
        assert fatal.is_fatal is True
        
        not_fatal = IBError("Recoverable", ib_error_code=1100)
        assert not_fatal.is_fatal is False
    
    def test_from_ib_error(self):
        """Test factory method from IB callback."""
        error = IBError.from_ib_error(
            req_id=123,
            error_code=504,
            error_string="Not connected"
        )
        assert error.ib_error_code == 504
        assert error.req_id == 123
        assert "Not connected" in error.message
    
    def test_from_ib_error_no_req_id(self):
        """Test factory method with -1 req_id."""
        error = IBError.from_ib_error(
            req_id=-1,
            error_code=1100,
            error_string="Connection lost"
        )
        assert error.req_id is None
    
    def test_unknown_error_code(self):
        """Test unknown error code handling."""
        error = IBError("Unknown", ib_error_code=99999)
        assert "Unknown IB error" in error.details["ib_error_description"]


class TestRateLimitExceeded:
    """Tests for RateLimitExceeded."""
    
    def test_rate_limit_basic(self):
        """Test basic rate limit error."""
        error = RateLimitExceeded()
        assert "Rate limit exceeded" in error.message
    
    def test_rate_limit_with_retry(self):
        """Test rate limit with retry after."""
        error = RateLimitExceeded(
            "Too many requests",
            retry_after=5.5
        )
        assert error.retry_after == 5.5
        assert error.details["retry_after_seconds"] == 5.5


class TestCircuitBreakerOpen:
    """Tests for CircuitBreakerOpen."""
    
    def test_circuit_breaker_basic(self):
        """Test basic circuit breaker error."""
        error = CircuitBreakerOpen()
        assert "Circuit breaker is open" in error.message
    
    def test_circuit_breaker_with_details(self):
        """Test circuit breaker with reset time and failure count."""
        error = CircuitBreakerOpen(
            "Service unavailable",
            reset_time=30.0,
            failure_count=5
        )
        assert error.reset_time == 30.0
        assert error.failure_count == 5
        assert error.details["failure_count"] == 5
        assert error.details["reset_time"] == 30.0


class TestHeartbeatTimeout:
    """Tests for HeartbeatTimeout."""
    
    def test_heartbeat_timeout_basic(self):
        """Test basic heartbeat timeout."""
        error = HeartbeatTimeout()
        assert "Heartbeat timeout" in error.message
    
    def test_heartbeat_timeout_with_details(self):
        """Test heartbeat timeout with details."""
        error = HeartbeatTimeout(
            "Connection may be lost",
            last_heartbeat=1234567890.0,
            timeout_seconds=30.0
        )
        assert error.last_heartbeat == 1234567890.0
        assert error.timeout_seconds == 30.0
        assert error.details["last_heartbeat"] == 1234567890.0
        assert error.details["timeout_seconds"] == 30.0
