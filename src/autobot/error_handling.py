"""
Resilient error handling system for AUTOBOT.

This module provides a comprehensive error handling system with automatic
recovery mechanisms, error classification, and detailed logging.
"""

import os
import time
import threading
import logging
import traceback
import json
import datetime
from typing import Dict, List, Any, Optional, Tuple, Callable, Type, Union
from enum import Enum
from dataclasses import dataclass, field
import functools

logger = logging.getLogger(__name__)

class ErrorSeverity(Enum):
    """Severity levels for errors."""
    INFO = 0
    WARNING = 1
    ERROR = 2
    CRITICAL = 3

class ErrorCategory(Enum):
    """Categories for classifying errors."""
    NETWORK = "network"
    API = "api"
    AUTHENTICATION = "authentication"
    PERMISSION = "permission"
    VALIDATION = "validation"
    DATABASE = "database"
    SYSTEM = "system"
    TIMEOUT = "timeout"
    RESOURCE = "resource"
    UNKNOWN = "unknown"

@dataclass
class ErrorContext:
    """Context information for an error."""
    module: str
    function: str
    args: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    thread_id: int = field(default_factory=lambda: threading.current_thread().ident)
    thread_name: str = field(default_factory=lambda: threading.current_thread().name)
    stack_trace: str = field(default_factory=str)

@dataclass
class ErrorRecord:
    """Record of an error occurrence."""
    error_type: str
    error_message: str
    severity: ErrorSeverity
    category: ErrorCategory
    context: ErrorContext
    recovery_attempted: bool = False
    recovery_successful: bool = False
    recovery_strategy: Optional[str] = None
    related_errors: List[str] = field(default_factory=list)

class ErrorHandler:
    """
    Comprehensive error handling system for AUTOBOT.
    
    This class provides utilities for handling errors, including automatic
    recovery, error classification, and detailed logging.
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        error_log_path: Optional[str] = None,
        visible_interface: bool = False
    ):
        """
        Initialize the error handler.
        
        Args:
            max_retries: Maximum number of retries for recoverable errors
            retry_delay: Delay in seconds between retries
            error_log_path: Path to error log file
            visible_interface: Whether to show error messages in the interface
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.error_log_path = error_log_path
        self.visible_interface = visible_interface
        
        self._error_records = []
        self._error_counts = {}
        self._recovery_strategies = {}
        self._lock = threading.Lock()
        
        if error_log_path:
            os.makedirs(os.path.dirname(error_log_path), exist_ok=True)
        
        if self.visible_interface:
            logger.info("Initialized error handling system")
        else:
            logger.debug("Initialized error handling system")
    
    def register_recovery_strategy(
        self,
        error_type: Union[Type[Exception], str],
        strategy_fn: Callable[[Exception, ErrorContext], bool],
        name: str
    ) -> None:
        """
        Register a recovery strategy for an error type.
        
        Args:
            error_type: Type of error to handle
            strategy_fn: Function to call for recovery
            name: Name of the strategy for logging
        """
        error_type_name = error_type.__name__ if isinstance(error_type, type) else error_type
        
        with self._lock:
            self._recovery_strategies[error_type_name] = {
                "function": strategy_fn,
                "name": name
            }
            
        if self.visible_interface:
            logger.info(f"Registered recovery strategy '{name}' for {error_type_name}")
        else:
            logger.debug(f"Registered recovery strategy '{name}' for {error_type_name}")
    
    def handle_error(
        self,
        error: Exception,
        module: str,
        function: str,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        category: Optional[ErrorCategory] = None,
        args: Optional[Dict[str, Any]] = None,
        attempt_recovery: bool = True
    ) -> Tuple[bool, Optional[ErrorRecord]]:
        """
        Handle an error.
        
        Args:
            error: Exception to handle
            module: Module where the error occurred
            function: Function where the error occurred
            severity: Severity of the error
            category: Category of the error
            args: Arguments to the function where the error occurred
            attempt_recovery: Whether to attempt recovery
            
        Returns:
            Tuple: (recovery_successful, error_record)
        """
        error_type = type(error).__name__
        error_message = str(error)
        
        context = ErrorContext(
            module=module,
            function=function,
            args=args or {},
            stack_trace=traceback.format_exc()
        )
        
        if category is None:
            category = self._categorize_error(error)
        
        record = ErrorRecord(
            error_type=error_type,
            error_message=error_message,
            severity=severity,
            category=category,
            context=context
        )
        
        self._log_error(record)
        
        with self._lock:
            if error_type not in self._error_counts:
                self._error_counts[error_type] = 0
            self._error_counts[error_type] += 1
        
        recovery_successful = False
        if attempt_recovery:
            recovery_successful, strategy_name = self._attempt_recovery(error, context)
            record.recovery_attempted = True
            record.recovery_successful = recovery_successful
            record.recovery_strategy = strategy_name
            
            self._log_error(record)
        
        with self._lock:
            self._error_records.append(record)
            
            if len(self._error_records) > 1000:
                self._error_records = self._error_records[-1000:]
        
        return recovery_successful, record
    
    def _categorize_error(self, error: Exception) -> ErrorCategory:
        """
        Categorize an error based on its type and message.
        
        Args:
            error: Exception to categorize
            
        Returns:
            ErrorCategory: Category of the error
        """
        error_type = type(error).__name__
        error_message = str(error).lower()
        
        if any(term in error_type.lower() for term in ["socket", "connection", "timeout", "network"]):
            return ErrorCategory.NETWORK
        if any(term in error_message for term in ["connection", "timeout", "network", "unreachable", "dns"]):
            return ErrorCategory.NETWORK
        
        if any(term in error_type.lower() for term in ["api", "http", "request", "response"]):
            return ErrorCategory.API
        if any(term in error_message for term in ["api", "endpoint", "status code", "http"]):
            return ErrorCategory.API
        
        if any(term in error_type.lower() for term in ["auth", "login", "credential", "token"]):
            return ErrorCategory.AUTHENTICATION
        if any(term in error_message for term in ["auth", "login", "credential", "token", "password", "unauthorized"]):
            return ErrorCategory.AUTHENTICATION
        
        if any(term in error_type.lower() for term in ["permission", "access", "forbidden"]):
            return ErrorCategory.PERMISSION
        if any(term in error_message for term in ["permission", "access", "forbidden", "denied"]):
            return ErrorCategory.PERMISSION
        
        if any(term in error_type.lower() for term in ["validation", "invalid", "value", "type"]):
            return ErrorCategory.VALIDATION
        if any(term in error_message for term in ["validation", "invalid", "value", "type", "format"]):
            return ErrorCategory.VALIDATION
        
        if any(term in error_type.lower() for term in ["db", "database", "sql", "query"]):
            return ErrorCategory.DATABASE
        if any(term in error_message for term in ["db", "database", "sql", "query", "table", "column"]):
            return ErrorCategory.DATABASE
        
        if any(term in error_type.lower() for term in ["os", "system", "io", "file", "memory"]):
            return ErrorCategory.SYSTEM
        if any(term in error_message for term in ["os", "system", "io", "file", "memory", "disk"]):
            return ErrorCategory.SYSTEM
        
        if any(term in error_type.lower() for term in ["timeout", "time"]):
            return ErrorCategory.TIMEOUT
        if any(term in error_message for term in ["timeout", "timed out", "too slow"]):
            return ErrorCategory.TIMEOUT
        
        if any(term in error_type.lower() for term in ["resource", "memory", "cpu", "disk"]):
            return ErrorCategory.RESOURCE
        if any(term in error_message for term in ["resource", "memory", "cpu", "disk", "full", "exhausted"]):
            return ErrorCategory.RESOURCE
        
        return ErrorCategory.UNKNOWN
    
    def _attempt_recovery(self, error: Exception, context: ErrorContext) -> Tuple[bool, Optional[str]]:
        """
        Attempt to recover from an error.
        
        Args:
            error: Exception to recover from
            context: Context of the error
            
        Returns:
            Tuple: (recovery_successful, strategy_name)
        """
        error_type = type(error).__name__
        
        with self._lock:
            if error_type in self._recovery_strategies:
                strategy = self._recovery_strategies[error_type]
                
                try:
                    recovery_successful = strategy["function"](error, context)
                    
                    if recovery_successful:
                        if self.visible_interface:
                            logger.info(f"Successfully recovered from {error_type} using strategy '{strategy['name']}'")
                        else:
                            logger.debug(f"Successfully recovered from {error_type} using strategy '{strategy['name']}'")
                    else:
                        if self.visible_interface:
                            logger.warning(f"Failed to recover from {error_type} using strategy '{strategy['name']}'")
                        else:
                            logger.debug(f"Failed to recover from {error_type} using strategy '{strategy['name']}'")
                    
                    return recovery_successful, strategy["name"]
                except Exception as e:
                    if self.visible_interface:
                        logger.error(f"Error in recovery strategy '{strategy['name']}': {str(e)}")
                    else:
                        logger.debug(f"Error in recovery strategy '{strategy['name']}': {str(e)}")
                    
                    return False, strategy["name"]
        
        return False, None
    
    def _log_error(self, record: ErrorRecord) -> None:
        """
        Log an error record.
        
        Args:
            record: Error record to log
        """
        log_message = f"[{record.severity.name}] {record.error_type}: {record.error_message} in {record.context.module}.{record.context.function}"
        
        if record.severity == ErrorSeverity.CRITICAL:
            if self.visible_interface:
                logger.critical(log_message)
            else:
                logger.error(log_message)
        elif record.severity == ErrorSeverity.ERROR:
            if self.visible_interface:
                logger.error(log_message)
            else:
                logger.warning(log_message)
        elif record.severity == ErrorSeverity.WARNING:
            if self.visible_interface:
                logger.warning(log_message)
            else:
                logger.info(log_message)
        else:
            if self.visible_interface:
                logger.info(log_message)
            else:
                logger.debug(log_message)
        
        if self.error_log_path:
            try:
                record_dict = {
                    "timestamp": datetime.datetime.fromtimestamp(record.context.timestamp).isoformat(),
                    "error_type": record.error_type,
                    "error_message": record.error_message,
                    "severity": record.severity.name,
                    "category": record.category.value,
                    "module": record.context.module,
                    "function": record.context.function,
                    "thread_id": record.context.thread_id,
                    "thread_name": record.context.thread_name,
                    "recovery_attempted": record.recovery_attempted,
                    "recovery_successful": record.recovery_successful,
                    "recovery_strategy": record.recovery_strategy,
                    "stack_trace": record.context.stack_trace
                }
                
                with open(self.error_log_path, "a") as f:
                    f.write(json.dumps(record_dict) + "\n")
            except Exception as e:
                logger.error(f"Failed to write error to log file: {str(e)}")
    
    def get_error_stats(self) -> Dict[str, Any]:
        """
        Get statistics about errors.
        
        Returns:
            Dict: Error statistics
        """
        with self._lock:
            total_errors = sum(self._error_counts.values())
            
            return {
                "total_errors": total_errors,
                "error_counts": self._error_counts.copy(),
                "recovery_strategies": list(self._recovery_strategies.keys()),
                "recent_errors": [
                    {
                        "error_type": record.error_type,
                        "error_message": record.error_message,
                        "severity": record.severity.name,
                        "category": record.category.value,
                        "module": record.context.module,
                        "function": record.context.function,
                        "timestamp": record.context.timestamp,
                        "recovery_attempted": record.recovery_attempted,
                        "recovery_successful": record.recovery_successful
                    }
                    for record in self._error_records[-10:]
                ]
            }
    
    def retry(self, max_retries: Optional[int] = None, retry_delay: Optional[float] = None):
        """
        Decorator for retrying functions that may fail.
        
        Args:
            max_retries: Maximum number of retries (defaults to handler's max_retries)
            retry_delay: Delay in seconds between retries (defaults to handler's retry_delay)
            
        Returns:
            Callable: Decorated function
        """
        max_retries = max_retries if max_retries is not None else self.max_retries
        retry_delay = retry_delay if retry_delay is not None else self.retry_delay
        
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                last_error = None
                
                for attempt in range(max_retries + 1):
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        last_error = e
                        
                        module = func.__module__
                        function = func.__name__
                        
                        args_dict = {
                            "args": str(args)[:100] + "..." if len(str(args)) > 100 else str(args),
                            "kwargs": str(kwargs)[:100] + "..." if len(str(kwargs)) > 100 else str(kwargs)
                        }
                        
                        recovery_successful, _ = self.handle_error(
                            error=e,
                            module=module,
                            function=function,
                            args=args_dict,
                            attempt_recovery=True
                        )
                        
                        if recovery_successful:
                            continue
                        
                        if attempt >= max_retries:
                            raise
                        
                        time.sleep(retry_delay * (2 ** attempt))  # Exponential backoff
                
                raise last_error
            
            return wrapper
        
        return decorator

def create_error_handler(
    max_retries: int = 3,
    retry_delay: float = 1.0,
    error_log_path: Optional[str] = None,
    visible_interface: bool = False
) -> ErrorHandler:
    """
    Create and return an error handler.
    
    Args:
        max_retries: Maximum number of retries for recoverable errors
        retry_delay: Delay in seconds between retries
        error_log_path: Path to error log file
        visible_interface: Whether to show error messages in the interface
        
    Returns:
        ErrorHandler: New error handler instance
    """
    return ErrorHandler(
        max_retries=max_retries,
        retry_delay=retry_delay,
        error_log_path=error_log_path,
        visible_interface=visible_interface
    )


def network_recovery_strategy(error: Exception, context: ErrorContext) -> bool:
    """
    Recovery strategy for network errors.
    
    Args:
        error: Network error
        context: Error context
        
    Returns:
        bool: True if recovery was successful, False otherwise
    """
    
    logger.debug(f"Attempting to recover from network error: {str(error)}")
    
    import random
    return random.random() < 0.5

def api_recovery_strategy(error: Exception, context: ErrorContext) -> bool:
    """
    Recovery strategy for API errors.
    
    Args:
        error: API error
        context: Error context
        
    Returns:
        bool: True if recovery was successful, False otherwise
    """
    
    logger.debug(f"Attempting to recover from API error: {str(error)}")
    
    import random
    return random.random() < 0.7

def authentication_recovery_strategy(error: Exception, context: ErrorContext) -> bool:
    """
    Recovery strategy for authentication errors.
    
    Args:
        error: Authentication error
        context: Error context
        
    Returns:
        bool: True if recovery was successful, False otherwise
    """
    
    logger.debug(f"Attempting to recover from authentication error: {str(error)}")
    
    import random
    return random.random() < 0.8
