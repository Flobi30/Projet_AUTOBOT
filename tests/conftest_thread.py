"""
Simplified conftest for thread management tests.

This conftest file is specifically designed for thread management tests
and does not depend on FastAPI to avoid compatibility issues.
"""

import sys
import os
import logging
import pytest

# Calculate absolute path to src/ directory
root = os.path.dirname(os.path.dirname(__file__))
src = os.path.join(root, "src")

# Add src/ to sys.path so pytest can see the package
if src not in sys.path:
    sys.path.append(src)

# Import thread cleanup fixture to ensure all threads are properly terminated
# The fixture is automatically used due to autouse=True
from thread_cleanup import thread_cleanup

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

@pytest.fixture(scope="session")
def thread_manager():
    """
    Provides a thread manager for testing.
    """
    from autobot.trading.ghosting_manager_thread_integration import GhostingThreadManager
    return GhostingThreadManager()
