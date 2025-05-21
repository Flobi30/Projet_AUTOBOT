"""
Protection CSRF pour AUTOBOT.
"""
import secrets
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer
from fastapi.security.utils import get_authorization_scheme_param

class CSRFProtection:
    def __init__(self, cookie_name: str = "csrf_token"):
        self.cookie_name = cookie_name
    
    def generate_token(self) -> str:
        return secrets.token_hex(32)
    
    async def validate_csrf_token(self, request: Request):
        csrf_cookie = request.cookies.get(self.cookie_name)
        csrf_form = request.headers.get("X-CSRF-Token")
        
        if not csrf_cookie or not csrf_form or csrf_cookie != csrf_form:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token manquant ou invalide"
            )
