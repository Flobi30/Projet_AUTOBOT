"""
AUTOBOT Rate Limiter

In-memory sliding window rate limiter for protecting sensitive endpoints.
"""

import time
from collections import defaultdict
from typing import Dict, List

from fastapi import HTTPException, Request


class RateLimiter:
    """Sliding window rate limiter."""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, List[float]] = defaultdict(list)

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"

    def _clean_old_requests(self, client_ip: str) -> None:
        now = time.time()
        cutoff = now - self.window_seconds
        self._requests[client_ip] = [
            t for t in self._requests[client_ip] if t > cutoff
        ]

    async def check(self, request: Request) -> None:
        client_ip = self._get_client_ip(request)
        self._clean_old_requests(client_ip)

        if len(self._requests[client_ip]) >= self.max_requests:
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please try again later."
            )

        self._requests[client_ip].append(time.time())


login_limiter = RateLimiter(max_requests=5, window_seconds=60)
financial_limiter = RateLimiter(max_requests=10, window_seconds=60)
