"""
Compatibility module for autobot.autobot_security.config.

This module provides backward compatibility for imports from the autobot.autobot_security.config namespace.
It redirects imports to the new module structure.
"""

import os
import sys
import warnings

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../../..')))

try:
    from src.autobot.autobot_security.config import SECRET_KEY, ALGORITHM
except ImportError:
    warnings.warn(
        "Could not import autobot_security.config module. Using fallback implementations.",
        ImportWarning,
        stacklevel=2
    )
    
    SECRET_KEY = os.getenv("JWT_SECRET", "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")
    ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
