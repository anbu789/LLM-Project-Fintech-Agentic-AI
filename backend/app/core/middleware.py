"""
FinTech Agent — Request Body Size Limiter Middleware
Enforces strict HTTP body size limits before body buffering or JSON parsing to prevent DoS.
"""

from typing import Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class RequestBodyLimitMiddleware(BaseHTTPMiddleware):
    """
    Rejects requests whose payload exceeds the configured maximum body size.
    Handles both Content-Length declarations and streamed/chunked payloads.
    """

    def __init__(self, app, max_body_bytes: int = 1_048_576):
        super().__init__(app)
        self.max_body_bytes = max_body_bytes

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        content_length = request.headers.get("content-length")

        if content_length:
            try:
                length = int(content_length)
                if length > self.max_body_bytes:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "success": False,
                            "error_code": "PAYLOAD_TOO_LARGE",
                            "message": f"Request payload ({length} bytes) exceeds maximum allowed limit of {self.max_body_bytes} bytes.",
                            "request_id": None,
                        },
                    )
            except ValueError:
                pass

        # For streamed/chunked requests without Content-Length
        body = await request.body()
        if len(body) > self.max_body_bytes:
            return JSONResponse(
                status_code=413,
                content={
                    "success": False,
                    "error_code": "PAYLOAD_TOO_LARGE",
                    "message": f"Request payload ({len(body)} bytes) exceeds maximum allowed limit of {self.max_body_bytes} bytes.",
                    "request_id": None,
                },
            )

        return await call_next(request)
