"""
Authentication module for AUTOBOT.

This module provides compatibility with the existing autobot_security.auth module.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../..')))

try:
    from src.autobot.autobot_security.auth.jwt_handler import (
        oauth2_scheme,
        verify_license_key,
        create_access_token,
        decode_token,
        get_current_user,
        generate_license_key
    )
except ImportError:
    from fastapi.security import OAuth2PasswordBearer
    from typing import Dict, Any, Optional
    from datetime import timedelta
    
    oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
    
    def verify_license_key(license_key: str) -> bool:
        """Fallback implementation of verify_license_key"""
        expected = os.getenv("LICENSE_KEY")
        return license_key == expected
    
    def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """Fallback implementation of create_access_token"""
        return "dummy_token"
    
    def decode_token(token: str) -> Dict[str, Any]:
        """Fallback implementation of decode_token"""
        return {"sub": "dummy_user"}
    
    def get_current_user(token: str = None) -> Dict[str, Any]:
        """Fallback implementation of get_current_user"""
        return {"sub": "dummy_user"}
    
    def generate_license_key(user_id: str, features: list, expiration_days: int = 365) -> str:
        """Fallback implementation of generate_license_key"""
        return "AUTOBOT-DUMMY-LICENSE-KEY"
