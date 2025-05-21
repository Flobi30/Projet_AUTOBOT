"""
AUTOBOT - Trading and Automation Framework
"""
import sys
import os

__version__ = "0.1.0"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

if 'pytest' in sys.modules:
    import autobot
    sys.modules['src.autobot'] = sys.modules['autobot']
    
    from autobot.autobot_guardian import get_logs
    from autobot.autobot_security.auth.jwt_handler import verify_license_key
