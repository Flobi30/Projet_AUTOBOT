"""
Logging module for AUTOBOT.

This module provides logging functionality for the AUTOBOT system.
"""

import logging
import os
from typing import Optional, List

def setup_logging(
    log_level: int = logging.INFO,
    log_format: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    log_file: Optional[str] = "autobot.log",
    handlers: Optional[List[logging.Handler]] = None
) -> None:
    """
    Set up logging for the AUTOBOT system.
    
    Args:
        log_level: Logging level
        log_format: Logging format
        log_file: Path to log file (None for no file logging)
        handlers: Additional handlers to add
    """
    handler_list = []
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(log_format))
    handler_list.append(console_handler)
    
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter(log_format))
        handler_list.append(file_handler)
    
    if handlers:
        handler_list.extend(handlers)
    
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=handler_list
    )
