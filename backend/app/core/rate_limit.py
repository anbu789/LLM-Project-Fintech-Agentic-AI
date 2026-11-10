"""
FinTech Agent — In-Memory Rate Limiting
Provides sliding-window rate limiting per client IP to prevent API abuse and denial of service.

Operational note:
This in-memory rate limiter tracks request counts within a single process.
If multiple worker processes (e.g. gunicorn/uvicorn workers) are deployed in production,
each worker maintains its own local bucket. For multi-node distributed rate limiting,
a centralized Redis or token bucket backing must be configured.
"""

import time
from collections import defaultdict
from typing import Dict, List
from fastapi import HTTPException, Request, status


class InMemoryRateLimiter:
    """Sliding-window rate limiter per client IP."""

    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.window_seconds = 60.0
        self._requests: Dict[str, List[float]] = defaultdict(list)

    def _clean_old_requests(self, ip: str, now: float) -> None:
        cutoff = now - self.window_seconds
        self._requests[ip] = [t for t in self._requests[ip] if t > cutoff]

    def is_allowed(self, ip: str) -> bool:
        now = time.time()
        self._clean_old_requests(ip, now)
        if len(self._requests[ip]) >= self.requests_per_minute:
            return False
        self._requests[ip].append(now)
        return True

    def reset(self) -> None:
        """Clears all tracked IP buckets (primarily used for unit testing)."""
        self._requests.clear()

    async def __call__(self, request: Request) -> None:
        # Resolve client IP safely
        client_ip = request.client.host if request.client else "127.0.0.1"
        # Check forwarded headers if present
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()

        if not self.is_allowed(client_ip):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "success": False,
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "message": f"Rate limit of {self.requests_per_minute} requests per minute exceeded. Please try again later.",
                    "request_id": None,
                },
            )


# Default endpoint limiters
chat_rate_limiter = InMemoryRateLimiter(requests_per_minute=60)
schema_search_rate_limiter = InMemoryRateLimiter(requests_per_minute=60)
schema_index_rate_limiter = InMemoryRateLimiter(requests_per_minute=5)
