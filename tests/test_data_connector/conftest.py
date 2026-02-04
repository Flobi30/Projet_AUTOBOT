"""Conftest for data connector tests - isolated from main conftest."""
import sys
import os

# Add src to path
root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
src = os.path.join(root, "src")
if src not in sys.path:
    sys.path.insert(0, src)

import pytest
