"""
JSON Structured Logging for AUTOBOT V2
Format: {"timestamp": "...", "level": "...", "event": "...", "data": {...}}
"""

import logging
import orjson
import sys
from datetime import datetime
from typing import Dict, Any, Optional

class JSONFormatter(logging.Formatter):
    """Formatter for structured JSON logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "file": record.filename,
            "line": record.lineno,
        }
        
        # Add extra fields if present
        if hasattr(record, 'extra_data'):
            log_data['data'] = record.extra_data
            
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
            
        return orjson.dumps(log_data, option=orjson.OPT_NON_STR_KEYS).decode('utf-8')


class StructuredLogger:
    """Wrapper for structured logging with extra data"""
    
    def __init__(self, name: str):
        self._logger = logging.getLogger(name)
        
    def _log(self, level: int, event: str, extra_data: Optional[Dict[str, Any]] = None):
        """Log with structured data"""
        extra = {'extra_data': extra_data} if extra_data else {}
        self._logger.log(level, event, extra=extra)
        
    def info(self, event: str, **kwargs):
        """Log info with structured data"""
        self._log(logging.INFO, event, kwargs if kwargs else None)
        
    def warning(self, event: str, **kwargs):
        """Log warning with structured data"""
        self._log(logging.WARNING, event, kwargs if kwargs else None)
        
    def error(self, event: str, **kwargs):
        """Log error with structured data"""
        self._log(logging.ERROR, event, kwargs if kwargs else None)
        
    def debug(self, event: str, **kwargs):
        """Log debug with structured data"""
        self._log(logging.DEBUG, event, kwargs if kwargs else None)
        
    def critical(self, event: str, **kwargs):
        """Log critical with structured data"""
        self._log(logging.CRITICAL, event, kwargs if kwargs else None)
        
    def exception(self, event: str, **kwargs):
        """Log exception with structured data"""
        extra = kwargs if kwargs else {}
        self._logger.exception(event, extra={'extra_data': extra})


def setup_structured_logging(
    level: int = logging.INFO,
    log_file: str = "autobot.log",
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    use_json: bool = True
) -> logging.Logger:
    """
    Setup structured logging with rotation
    
    Args:
        level: Logging level
        log_file: Path to log file
        max_bytes: Max size before rotation
        backup_count: Number of backup files to keep
        use_json: Use JSON format (True) or text format (False)
    """
    from logging.handlers import RotatingFileHandler
    
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Clear existing handlers
    root_logger.handlers = []
    
    # Console handler (text for readability)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # File handler with rotation (JSON for parsing)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count
    )
    file_handler.setLevel(level)
    
    if use_json:
        file_handler.setFormatter(JSONFormatter())
    else:
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
    root_logger.addHandler(file_handler)
    
    return root_logger


def get_structured_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance"""
    return StructuredLogger(name)
