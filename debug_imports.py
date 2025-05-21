"""
Debug script to identify circular imports in the codebase.
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

print("Attempting to import modules...")

try:
    print("Importing src.autobot...")
    import src.autobot
    print("Success: src.autobot")
except ImportError as e:
    print(f"Error importing src.autobot: {e}")

try:
    print("Importing src.autobot.main...")
    import src.autobot.main
    print("Success: src.autobot.main")
except ImportError as e:
    print(f"Error importing src.autobot.main: {e}")

try:
    print("Importing src.autobot.ui...")
    import src.autobot.ui
    print("Success: src.autobot.ui")
except ImportError as e:
    print(f"Error importing src.autobot.ui: {e}")

try:
    print("Importing src.autobot.ui.simplified_dashboard_routes...")
    import src.autobot.ui.simplified_dashboard_routes
    print("Success: src.autobot.ui.simplified_dashboard_routes")
except ImportError as e:
    print(f"Error importing src.autobot.ui.simplified_dashboard_routes: {e}")

try:
    print("Importing src.autobot.ui.mobile_routes...")
    import src.autobot.ui.mobile_routes
    print("Success: src.autobot.ui.mobile_routes")
except ImportError as e:
    print(f"Error importing src.autobot.ui.mobile_routes: {e}")

print("Import tests completed.")
