"""
Compatibility module for existing imports.

This module provides backward compatibility for imports from the autobot.autobot namespace.
It redirects imports to the new module structure.
"""

import warnings
import sys

warnings.warn(
    "The module 'autobot.autobot' is deprecated and will be removed in a future version. "
    "Use the modules 'autobot.core', 'autobot.security', etc. instead.",
    DeprecationWarning,
    stacklevel=2
)

import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

try:
    from src.autobot.core.monitoring import get_system_status, get_system_metrics, get_system_logs
except ImportError:
    def get_system_status():
        return {"status": "ok"}
        
    def get_system_metrics():
        return {"cpu": 0, "memory": 0, "disk": 0}
        
    def get_system_logs():
        return {"logs": []}
