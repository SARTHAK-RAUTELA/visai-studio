"""
Optional API key gate — Phase 5+.
Set API_KEY in .env to enable. If unset, all requests pass through (dev mode).
Send key via header:  X-API-Key: <key>
Or query string:       ?api_key=<key>
"""

import os

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Paths that never require auth
_OPEN_PATHS = {"/", "/health", "/docs", "/openapi.json", "/redoc"}


class APIKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._key = os.getenv("API_KEY", "").strip()

    async def dispatch(self, request, call_next):
        if not self._key or request.url.path in _OPEN_PATHS:
            return await call_next(request)

        provided = (
            request.headers.get("X-API-Key")
            or request.query_params.get("api_key")
            or ""
        )
        if provided != self._key:
            return JSONResponse(
                {"error": "Invalid or missing API key"},
                status_code=401,
            )
        return await call_next(request)
