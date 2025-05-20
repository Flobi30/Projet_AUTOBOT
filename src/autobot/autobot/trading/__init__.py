"""
Compatibility module for autobot.trading.

This module provides backward compatibility for imports from the autobot.trading namespace.
It redirects imports to the new module structure.
"""

import sys
import os
import warnings

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../../..')))

try:
    from src.autobot.trading import *
except ImportError:
    warnings.warn(
        "Could not import trading module. Using fallback implementations.",
        ImportWarning,
        stacklevel=2
    )
