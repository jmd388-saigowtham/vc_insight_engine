from __future__ import annotations

import time
from collections import defaultdict

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiter.

    - General endpoints: 500 requests/minute
    - Upload endpoints: 50 requests/minute
    """

    def __init__(self, app, general_limit: int = 500, upload_limit: int = 50, window: int = 60) -> None:  # noqa: ANN001
        super().__init__(app)
        self.general_limit = general_limit
        self.upload_limit = upload_limit
        self.window = window
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _is_upload_path(self, path: str) -> bool:
        return "/upload" in path

    def _check_rate(self, key: str, limit: int) -> bool:
        now = time.monotonic()
        timestamps = self._requests[key]
        # Remove timestamps outside the window
        cutoff = now - self.window
        self._requests[key] = [t for t in timestamps if t > cutoff]
        if len(self._requests[key]) >= limit:
            return False
        self._requests[key].append(now)
        return True

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        client_ip = self._get_client_ip(request)
        path = request.url.path

        if self._is_upload_path(path):
            key = f"upload:{client_ip}"
            limit = self.upload_limit
        else:
            key = f"general:{client_ip}"
            limit = self.general_limit

        if not self._check_rate(key, limit):
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again later."},
            )

        return await call_next(request)
