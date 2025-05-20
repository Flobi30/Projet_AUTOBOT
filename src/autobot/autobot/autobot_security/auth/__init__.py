"""
Compatibility module for autobot.autobot_security.auth.

This module provides backward compatibility for imports from the autobot.autobot_security.auth namespace.
It redirects imports to the new module structure.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../../../..')))

try:
    from src.autobot.autobot_security.auth import *
except ImportError:
    import warnings
    warnings.warn(
        "Could not import autobot_security.auth module. Using fallback implementations.",
        ImportWarning,
        stacklevel=2
    )
