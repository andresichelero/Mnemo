"""API key authentication middleware.

All requests to /api/* require a valid X-API-Key header,
except for the health endpoint and OpenAPI docs.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# Paths that do NOT require authentication
_PUBLIC_PATHS = frozenset({
    "/api/v1/health",
    "/docs",
    "/redoc",
    "/openapi.json",
})


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Reject requests without a valid API key."""

    def __init__(self, app, api_key: str):
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Allow public paths and non-API paths
        if path in _PUBLIC_PATHS or not path.startswith("/api/"):
            return await call_next(request)

        # Check API key header
        provided_key = request.headers.get("X-API-Key", "")
        if not provided_key or provided_key != self.api_key:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid API key", "code": "AUTH_REQUIRED"},
            )

        return await call_next(request)
