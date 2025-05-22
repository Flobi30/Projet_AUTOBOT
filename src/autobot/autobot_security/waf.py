"""
Middleware WAF (Web Application Firewall) pour filtrer les requêtes malveillantes.
"""
import re
import os
from typing import List, Dict, Set
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, RedirectResponse, Response

SQL_INJECTION_PATTERNS = [
    r"(\b|')SELECT(\b|')",
    r"(\b|')INSERT(\b|')",
    r"(\b|')UPDATE(\b|')",
    r"(\b|')DELETE(\b|')",
    r"(\b|')DROP(\b|')",
    r"(\b|')UNION(\b|')",
    r";.*--",
    r"--.*",
    r"\/\*.*\*\/",
    r"#.*$"
]

XSS_PATTERNS = [
    r"<script.*>",
    r"javascript:",
    r"onerror=",
    r"onload=",
    r"onclick=",
    r"onmouseover=",
    r"document\.cookie",
    r"document\.location",
    r"eval\(",
    r"setTimeout\(",
    r"setInterval\(",
    r"new Function\("
]

PATH_TRAVERSAL_PATTERNS = [
    r"\.\.\/",
    r"\.\.\\",
    r"%2e%2e%2f",
    r"%252e%252e%252f",
    r"%c0%ae%c0%ae%c0%af"
]

ATTACK_PATTERNS = SQL_INJECTION_PATTERNS + XSS_PATTERNS + PATH_TRAVERSAL_PATTERNS

class WAFMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, **kwargs):
        super().__init__(app)
        self.compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in ATTACK_PATTERNS]
        self.suspicious_ips: Set[str] = set()
        self.max_strikes = int(os.getenv("AUTOBOT_WAF_MAX_STRIKES", "3"))

    async def is_attack(self, request: Request) -> bool:
        """Vérifie si la requête contient des patterns d'attaque."""
        for pattern in self.compiled_patterns:
            if pattern.search(str(request.url)):
                return True
        
        for header, value in request.headers.items():
            for pattern in self.compiled_patterns:
                if pattern.search(value):
                    return True
        
        for param, value in request.query_params.items():
            for pattern in self.compiled_patterns:
                if pattern.search(value):
                    return True
        
        if request.method == "POST":
            try:
                body = await request.body()
                body_str = body.decode("utf-8")
                for pattern in self.compiled_patterns:
                    if pattern.search(body_str):
                        return True
            except:
                pass
        
        return False

    async def dispatch(self, request: Request, call_next):
        """
        Middleware qui filtre les requêtes malveillantes.
        """
        client_ip = request.client.host
        
        if await self.is_attack(request):
            self.suspicious_ips.add(client_ip)
            print(f"⚠️ [SECURITY] Attaque potentielle détectée depuis l'IP {client_ip}: {request.url}")
            
            return JSONResponse(
                status_code=403,
                content={"detail": "Accès refusé - Requête potentiellement malveillante"}
            )
        
        return await call_next(request)
        
    def get_suspicious_ips(self) -> Set[str]:
        """Retourne la liste des IPs suspectes."""
        return self.suspicious_ips
