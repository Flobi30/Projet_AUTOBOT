"""
Custom exceptions for the Data Connector module.

Provides structured error handling for IB-specific errors (502, 504, 1100)
and general connection issues.
"""

from typing import Optional, Dict, Any


class DataConnectorError(Exception):
    """Base exception for all data connector errors."""
    
    def __init__(
        self,
        message: str,
        error_code: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for JSON logging."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "error_code": self.error_code,
            "details": self.details,
        }


class ConnectionError(DataConnectorError):
    """Raised when connection to broker fails."""
    pass


class ReconnectionError(DataConnectorError):
    """Raised when reconnection attempts are exhausted."""
    
    def __init__(
        self,
        message: str,
        attempts: int,
        last_error: Optional[Exception] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.attempts = attempts
        self.last_error = last_error
        self.details["attempts"] = attempts
        if last_error:
            self.details["last_error"] = str(last_error)


class IBError(DataConnectorError):
    """
    Interactive Brokers specific error.
    
    Handles IB error codes:
    - 502: Couldn't connect to TWS
    - 504: Not connected
    - 1100: Connectivity between IB and TWS has been lost
    """
    
    IB_ERROR_CODES = {
        502: "Couldn't connect to TWS. Confirm that 'Enable ActiveX and Socket Clients' is enabled.",
        504: "Not connected. Please ensure TWS/Gateway is running.",
        1100: "Connectivity between IB and TWS has been lost.",
        1101: "Connectivity between IB and TWS has been restored - data lost.",
        1102: "Connectivity between IB and TWS has been restored - data maintained.",
        2103: "Market data farm connection is broken.",
        2104: "Market data farm connection is OK.",
        2105: "Historical data farm connection is broken.",
        2106: "Historical data farm connection is OK.",
        2107: "Historical data farm connection is inactive.",
        2108: "Market data farm connection is inactive.",
        2110: "Connectivity between TWS and server is broken.",
    }
    
    RECOVERABLE_CODES = {1100, 1101, 2103, 2105, 2107, 2108, 2110}
    FATAL_CODES = {502, 504}
    
    def __init__(
        self,
        message: str,
        ib_error_code: int,
        req_id: Optional[int] = None,
        **kwargs
    ):
        super().__init__(message, error_code=ib_error_code, **kwargs)
        self.ib_error_code = ib_error_code
        self.req_id = req_id
        self.details["ib_error_code"] = ib_error_code
        self.details["ib_error_description"] = self.IB_ERROR_CODES.get(
            ib_error_code, "Unknown IB error"
        )
        if req_id is not None:
            self.details["req_id"] = req_id
    
    @property
    def is_recoverable(self) -> bool:
        """Check if this error is recoverable through reconnection."""
        return self.ib_error_code in self.RECOVERABLE_CODES
    
    @property
    def is_fatal(self) -> bool:
        """Check if this error is fatal and requires manual intervention."""
        return self.ib_error_code in self.FATAL_CODES
    
    @classmethod
    def from_ib_error(
        cls,
        req_id: int,
        error_code: int,
        error_string: str
    ) -> "IBError":
        """Create IBError from IB callback parameters."""
        message = f"IB Error {error_code}: {error_string}"
        return cls(
            message=message,
            ib_error_code=error_code,
            req_id=req_id if req_id != -1 else None,
        )


class RateLimitExceeded(DataConnectorError):
    """Raised when rate limit is exceeded."""
    
    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[float] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after
        if retry_after:
            self.details["retry_after_seconds"] = retry_after


class CircuitBreakerOpen(DataConnectorError):
    """Raised when circuit breaker is open and requests are blocked."""
    
    def __init__(
        self,
        message: str = "Circuit breaker is open",
        reset_time: Optional[float] = None,
        failure_count: int = 0,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.reset_time = reset_time
        self.failure_count = failure_count
        self.details["failure_count"] = failure_count
        if reset_time:
            self.details["reset_time"] = reset_time


class HeartbeatTimeout(DataConnectorError):
    """Raised when heartbeat monitoring detects connection loss."""
    
    def __init__(
        self,
        message: str = "Heartbeat timeout - connection may be lost",
        last_heartbeat: Optional[float] = None,
        timeout_seconds: Optional[float] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.last_heartbeat = last_heartbeat
        self.timeout_seconds = timeout_seconds
        if last_heartbeat:
            self.details["last_heartbeat"] = last_heartbeat
        if timeout_seconds:
            self.details["timeout_seconds"] = timeout_seconds
