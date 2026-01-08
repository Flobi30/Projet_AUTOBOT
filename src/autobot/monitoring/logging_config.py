"""
AUTOBOT Logging Configuration

Advanced logging with:
- Log rotation (100MB per file, 10 files max)
- Gzip compression for old logs
- 30-day retention
- Structured logging (JSON format)
- Multiple log levels and handlers
- Alerting integration
"""

import logging
import logging.handlers
import gzip
import os
import shutil
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
import threading
import time


class GzipRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """
    Rotating file handler that compresses rotated files with gzip.
    """
    
    def __init__(
        self,
        filename: str,
        mode: str = 'a',
        maxBytes: int = 0,
        backupCount: int = 0,
        encoding: str = None,
        delay: bool = False,
    ):
        super().__init__(
            filename,
            mode=mode,
            maxBytes=maxBytes,
            backupCount=backupCount,
            encoding=encoding,
            delay=delay,
        )
    
    def doRollover(self):
        """
        Do a rollover and compress the rotated file.
        """
        if self.stream:
            self.stream.close()
            self.stream = None
        
        if self.backupCount > 0:
            # Rotate existing backup files
            for i in range(self.backupCount - 1, 0, -1):
                sfn = self.rotation_filename(f"{self.baseFilename}.{i}.gz")
                dfn = self.rotation_filename(f"{self.baseFilename}.{i + 1}.gz")
                if os.path.exists(sfn):
                    if os.path.exists(dfn):
                        os.remove(dfn)
                    os.rename(sfn, dfn)
            
            # Compress the current log file
            dfn = self.rotation_filename(f"{self.baseFilename}.1.gz")
            if os.path.exists(dfn):
                os.remove(dfn)
            
            if os.path.exists(self.baseFilename):
                with open(self.baseFilename, 'rb') as f_in:
                    with gzip.open(dfn, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                os.remove(self.baseFilename)
        
        if not self.delay:
            self.stream = self._open()


class JsonFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.
    """
    
    def __init__(self, include_extra: bool = True):
        super().__init__()
        self.include_extra = include_extra
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields
        if self.include_extra:
            for key, value in record.__dict__.items():
                if key not in [
                    'name', 'msg', 'args', 'created', 'filename', 'funcName',
                    'levelname', 'levelno', 'lineno', 'module', 'msecs',
                    'pathname', 'process', 'processName', 'relativeCreated',
                    'stack_info', 'exc_info', 'exc_text', 'thread', 'threadName',
                    'message', 'asctime'
                ]:
                    try:
                        json.dumps(value)  # Check if serializable
                        log_data[key] = value
                    except (TypeError, ValueError):
                        log_data[key] = str(value)
        
        return json.dumps(log_data)


class AlertHandler(logging.Handler):
    """
    Handler that triggers alerts for critical log messages.
    """
    
    def __init__(
        self,
        alert_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        min_level: int = logging.ERROR,
    ):
        super().__init__(level=min_level)
        self.alert_callback = alert_callback
        self.alert_history: List[Dict[str, Any]] = []
        self.max_history = 100
        self._lock = threading.Lock()
    
    def emit(self, record: logging.LogRecord):
        """Emit an alert for the log record"""
        alert = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        if record.exc_info:
            alert["exception"] = self.formatException(record.exc_info)
        
        with self._lock:
            self.alert_history.append(alert)
            if len(self.alert_history) > self.max_history:
                self.alert_history = self.alert_history[-self.max_history:]
        
        if self.alert_callback:
            try:
                self.alert_callback(alert)
            except Exception:
                pass  # Don't let alert failures break logging
    
    def get_recent_alerts(self, count: int = 20) -> List[Dict[str, Any]]:
        """Get recent alerts"""
        with self._lock:
            return self.alert_history[-count:]


class LogRetentionManager:
    """
    Manages log file retention and cleanup.
    """
    
    def __init__(
        self,
        log_dir: str,
        retention_days: int = 30,
        check_interval_hours: int = 24,
    ):
        self.log_dir = Path(log_dir)
        self.retention_days = retention_days
        self.check_interval = timedelta(hours=check_interval_hours)
        
        self._stop_event = threading.Event()
        self._cleanup_thread: Optional[threading.Thread] = None
    
    def start(self):
        """Start the retention cleanup thread"""
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            return
        
        self._stop_event.clear()
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True,
        )
        self._cleanup_thread.start()
    
    def stop(self):
        """Stop the retention cleanup thread"""
        self._stop_event.set()
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5)
    
    def _cleanup_loop(self):
        """Background cleanup loop"""
        while not self._stop_event.is_set():
            try:
                self.cleanup_old_logs()
            except Exception as e:
                logging.error(f"Error during log cleanup: {e}")
            
            # Wait for next check
            self._stop_event.wait(self.check_interval.total_seconds())
    
    def cleanup_old_logs(self) -> int:
        """
        Remove log files older than retention period.
        
        Returns:
            Number of files removed
        """
        if not self.log_dir.exists():
            return 0
        
        cutoff = datetime.utcnow() - timedelta(days=self.retention_days)
        removed = 0
        
        for log_file in self.log_dir.glob("*.log*"):
            try:
                mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                if mtime < cutoff:
                    log_file.unlink()
                    removed += 1
            except Exception:
                pass
        
        if removed > 0:
            logging.info(f"Removed {removed} old log files")
        
        return removed
    
    def get_log_stats(self) -> Dict[str, Any]:
        """Get statistics about log files"""
        if not self.log_dir.exists():
            return {"total_files": 0, "total_size_bytes": 0}
        
        total_files = 0
        total_size = 0
        oldest_file = None
        newest_file = None
        
        for log_file in self.log_dir.glob("*.log*"):
            try:
                stat = log_file.stat()
                total_files += 1
                total_size += stat.st_size
                
                mtime = datetime.fromtimestamp(stat.st_mtime)
                if oldest_file is None or mtime < oldest_file:
                    oldest_file = mtime
                if newest_file is None or mtime > newest_file:
                    newest_file = mtime
            except Exception:
                pass
        
        return {
            "total_files": total_files,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "oldest_file": oldest_file.isoformat() if oldest_file else None,
            "newest_file": newest_file.isoformat() if newest_file else None,
            "retention_days": self.retention_days,
        }


class LoggingManager:
    """
    Central logging manager for AUTOBOT.
    
    Configures logging with:
    - Rotating file handlers with gzip compression
    - JSON structured logging
    - Console output
    - Alert handling for critical messages
    - Log retention management
    """
    
    # Default settings per user requirements
    DEFAULT_MAX_BYTES = 100 * 1024 * 1024  # 100 MB
    DEFAULT_BACKUP_COUNT = 10
    DEFAULT_RETENTION_DAYS = 30
    
    def __init__(
        self,
        log_dir: str = "/app/logs",
        max_bytes: int = DEFAULT_MAX_BYTES,
        backup_count: int = DEFAULT_BACKUP_COUNT,
        retention_days: int = DEFAULT_RETENTION_DAYS,
        json_format: bool = True,
        console_output: bool = True,
        alert_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.log_dir = Path(log_dir)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.retention_days = retention_days
        self.json_format = json_format
        self.console_output = console_output
        self.alert_callback = alert_callback
        
        # Ensure log directory exists
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Handlers
        self.handlers: Dict[str, logging.Handler] = {}
        self.alert_handler: Optional[AlertHandler] = None
        
        # Retention manager
        self.retention_manager = LogRetentionManager(
            log_dir=str(self.log_dir),
            retention_days=retention_days,
        )
        
        # Configure logging
        self._configure_logging()
    
    def _configure_logging(self):
        """Configure the logging system"""
        # Get root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        
        # Remove existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # Create formatters
        if self.json_format:
            file_formatter = JsonFormatter()
        else:
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        
        console_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(name)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # Main log file (all levels)
        main_handler = GzipRotatingFileHandler(
            filename=str(self.log_dir / "autobot.log"),
            maxBytes=self.max_bytes,
            backupCount=self.backup_count,
            encoding='utf-8',
        )
        main_handler.setLevel(logging.DEBUG)
        main_handler.setFormatter(file_formatter)
        root_logger.addHandler(main_handler)
        self.handlers['main'] = main_handler
        
        # Error log file (errors and above)
        error_handler = GzipRotatingFileHandler(
            filename=str(self.log_dir / "autobot_error.log"),
            maxBytes=self.max_bytes,
            backupCount=self.backup_count,
            encoding='utf-8',
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(file_formatter)
        root_logger.addHandler(error_handler)
        self.handlers['error'] = error_handler
        
        # Trading log file
        trading_handler = GzipRotatingFileHandler(
            filename=str(self.log_dir / "trading.log"),
            maxBytes=self.max_bytes,
            backupCount=self.backup_count,
            encoding='utf-8',
        )
        trading_handler.setLevel(logging.INFO)
        trading_handler.setFormatter(file_formatter)
        self.handlers['trading'] = trading_handler
        
        # Create trading logger
        trading_logger = logging.getLogger('autobot.trading')
        trading_logger.addHandler(trading_handler)
        
        # Provider log file
        provider_handler = GzipRotatingFileHandler(
            filename=str(self.log_dir / "providers.log"),
            maxBytes=self.max_bytes,
            backupCount=self.backup_count,
            encoding='utf-8',
        )
        provider_handler.setLevel(logging.INFO)
        provider_handler.setFormatter(file_formatter)
        self.handlers['provider'] = provider_handler
        
        # Create provider logger
        provider_logger = logging.getLogger('autobot.providers')
        provider_logger.addHandler(provider_handler)
        
        # Risk log file
        risk_handler = GzipRotatingFileHandler(
            filename=str(self.log_dir / "risk.log"),
            maxBytes=self.max_bytes,
            backupCount=self.backup_count,
            encoding='utf-8',
        )
        risk_handler.setLevel(logging.INFO)
        risk_handler.setFormatter(file_formatter)
        self.handlers['risk'] = risk_handler
        
        # Create risk logger
        risk_logger = logging.getLogger('autobot.risk')
        risk_logger.addHandler(risk_handler)
        
        # Console handler
        if self.console_output:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(console_formatter)
            root_logger.addHandler(console_handler)
            self.handlers['console'] = console_handler
        
        # Alert handler
        self.alert_handler = AlertHandler(
            alert_callback=self.alert_callback,
            min_level=logging.ERROR,
        )
        root_logger.addHandler(self.alert_handler)
        self.handlers['alert'] = self.alert_handler
    
    def start_retention_manager(self):
        """Start the log retention manager"""
        self.retention_manager.start()
    
    def stop_retention_manager(self):
        """Stop the log retention manager"""
        self.retention_manager.stop()
    
    def get_recent_alerts(self, count: int = 20) -> List[Dict[str, Any]]:
        """Get recent alerts"""
        if self.alert_handler:
            return self.alert_handler.get_recent_alerts(count)
        return []
    
    def get_log_stats(self) -> Dict[str, Any]:
        """Get log file statistics"""
        return self.retention_manager.get_log_stats()
    
    def set_log_level(self, logger_name: str, level: str):
        """Set log level for a specific logger"""
        logger = logging.getLogger(logger_name)
        level_num = getattr(logging, level.upper(), logging.INFO)
        logger.setLevel(level_num)
    
    def add_custom_handler(
        self,
        name: str,
        filename: str,
        level: int = logging.INFO,
        logger_name: Optional[str] = None,
    ):
        """Add a custom log handler"""
        handler = GzipRotatingFileHandler(
            filename=str(self.log_dir / filename),
            maxBytes=self.max_bytes,
            backupCount=self.backup_count,
            encoding='utf-8',
        )
        handler.setLevel(level)
        
        if self.json_format:
            handler.setFormatter(JsonFormatter())
        else:
            handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
        
        self.handlers[name] = handler
        
        if logger_name:
            logger = logging.getLogger(logger_name)
            logger.addHandler(handler)
        else:
            logging.getLogger().addHandler(handler)
    
    def force_rotation(self, handler_name: str = 'main'):
        """Force log rotation for a specific handler"""
        handler = self.handlers.get(handler_name)
        if handler and isinstance(handler, GzipRotatingFileHandler):
            handler.doRollover()


# Singleton instance
_logging_manager_instance: Optional[LoggingManager] = None


def get_logging_manager(
    log_dir: str = "/app/logs",
    **kwargs,
) -> LoggingManager:
    """Get or create the singleton LoggingManager instance"""
    global _logging_manager_instance
    
    if _logging_manager_instance is None:
        _logging_manager_instance = LoggingManager(log_dir=log_dir, **kwargs)
    
    return _logging_manager_instance


def setup_logging(
    log_dir: str = "/app/logs",
    json_format: bool = True,
    console_output: bool = True,
    alert_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> LoggingManager:
    """
    Convenience function to set up logging.
    
    Args:
        log_dir: Directory for log files
        json_format: Use JSON format for log files
        console_output: Enable console output
        alert_callback: Callback for critical alerts
        
    Returns:
        LoggingManager instance
    """
    manager = get_logging_manager(
        log_dir=log_dir,
        json_format=json_format,
        console_output=console_output,
        alert_callback=alert_callback,
    )
    manager.start_retention_manager()
    return manager
