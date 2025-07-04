"""
Simple authentication module for AUTOBOT local testing
Replaces missing autobot_security module
"""

from typing import Optional
from fastapi import HTTPException, status
from pydantic import BaseModel

class User(BaseModel):
    """Simple user model for authentication"""
    id: str = "autobot_user"
    username: str = "AUTOBOT"
    email: Optional[str] = None

class UserManager:
    """Simple user manager for local testing"""
    
    def __init__(self):
        self.default_user = User(id="autobot_user", username="AUTOBOT")
    
    def get_user_by_id(self, user_id: str) -> User:
        return self.default_user
    
    def update_user_data(self, user_id: str, field: str, value: any):
        """Update user data - placeholder for local testing"""
        pass

def get_current_user() -> User:
    """
    Simple authentication function for local testing
    Returns default AUTOBOT user
    """
    return User(id="autobot_user", username="AUTOBOT")

__all__ = ["User", "UserManager", "get_current_user"]
