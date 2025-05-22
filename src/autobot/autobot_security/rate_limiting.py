"""
Middleware de limitation de taux pour prévenir les attaques par force brute.
"""
import time
import os
from typing import Dict, Tuple, List
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, RedirectResponse

DEFAULT_RATE_LIMIT = int(os.getenv("AUTOBOT_RATE_LIMIT", "5"))  # 5 requêtes
DEFAULT_RATE_LIMIT_WINDOW = int(os.getenv("AUTOBOT_RATE_LIMIT_WINDOW", "60"))  # 60 secondes
DEFAULT_BLOCK_DURATION = int(os.getenv("AUTOBOT_BLOCK_DURATION", "300"))  # 5 minutes de blocage

class RateLimitingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, paths_to_limit=["/login"], **kwargs):
        super().__init__(app)
        self.paths_to_limit = paths_to_limit
        self.rate_limit = kwargs.get("rate_limit", DEFAULT_RATE_LIMIT)
        self.rate_limit_window = kwargs.get("rate_limit_window", DEFAULT_RATE_LIMIT_WINDOW)
        self.block_duration = kwargs.get("block_duration", DEFAULT_BLOCK_DURATION)
        self.ip_requests: Dict[str, List[float]] = {}  # IP -> liste de timestamps
        self.blocked_ips: Dict[str, float] = {}  # IP -> timestamp de fin de blocage

    async def dispatch(self, request: Request, call_next):
        """
        Middleware qui limite le nombre de requêtes par IP pour les chemins spécifiés.
        """
        client_ip = request.client.host
        path = request.url.path
        
        if client_ip in self.blocked_ips:
            if time.time() < self.blocked_ips[client_ip]:
                if request.url.path in self.paths_to_limit:
                    print(f"🚫 [SECURITY] Tentative d'accès bloquée depuis l'IP {client_ip}")
                    return RedirectResponse(url=f"/login?error=Trop+de+tentatives+échouées.+Réessayez+dans+quelques+minutes.", status_code=303)
            else:
                del self.blocked_ips[client_ip]
                if client_ip in self.ip_requests:
                    del self.ip_requests[client_ip]
        
        if path in self.paths_to_limit:
            current_time = time.time()
            
            if client_ip not in self.ip_requests:
                self.ip_requests[client_ip] = []
            
            self.ip_requests[client_ip] = [t for t in self.ip_requests[client_ip] if current_time - t < self.rate_limit_window]
            
            if len(self.ip_requests[client_ip]) >= self.rate_limit:
                self.blocked_ips[client_ip] = current_time + self.block_duration
                print(f"🚫 [SECURITY] IP {client_ip} bloquée pour {self.block_duration} secondes après {self.rate_limit} tentatives")
                return RedirectResponse(url=f"/login?error=Trop+de+tentatives+échouées.+Réessayez+dans+quelques+minutes.", status_code=303)
            
            self.ip_requests[client_ip].append(current_time)
        
        return await call_next(request)
