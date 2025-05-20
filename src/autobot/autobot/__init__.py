"""
Compatibility module for existing imports.

This module provides backward compatibility for imports from the autobot.autobot namespace.
It redirects imports to the new module structure.
"""

import warnings

warnings.warn(
    "The module 'autobot.autobot' is deprecated and will be removed in a future version. "
    "Use the modules 'autobot.core', 'autobot.security', etc. instead.",
    DeprecationWarning,
    stacklevel=2
)

from autobot.core.monitoring import get_system_status, get_system_metrics, get_system_logs
