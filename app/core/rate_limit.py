import time
from collections import deque

from fastapi import Request, status

from app.core.config import get_settings
from app.core.exceptions import AppError


class SlidingWindowRateLimiter:
    """In-memory per-IP sliding window rate limiter for auth endpoints."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._last_sweep: float = 0.0

    def _sweep_expired(self, now: float, window_seconds: int) -> None:
        cutoff = now - window_seconds
        stale_keys = [
            k for k, bucket in self._hits.items() if not bucket or bucket[-1] <= cutoff
        ]
        for k in stale_keys:
            del self._hits[k]
        self._last_sweep = now

    def check(self, key: str, max_requests: int, window_seconds: int) -> None:
        now = time.monotonic()
        if now - self._last_sweep >= window_seconds:
            self._sweep_expired(now, window_seconds)

        cutoff = now - window_seconds
        bucket = self._hits.get(key)
        if bucket is None:
            bucket = deque()
            self._hits[key] = bucket

        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

        if len(bucket) >= max_requests:
            raise AppError(
                error_code="RATE_LIMIT_EXCEEDED",
                message="Too many requests. Please try again later.",
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                details={"retry_after_seconds": window_seconds},
            )

        bucket.append(now)

    def reset(self) -> None:
        self._hits.clear()
        self._last_sweep = 0.0


auth_rate_limiter = SlidingWindowRateLimiter()


async def enforce_auth_rate_limit(request: Request) -> None:
    settings = get_settings()
    client_ip = request.client.host if request.client else "unknown"
    key = f"{client_ip}:{request.url.path}"
    auth_rate_limiter.check(
        key=key,
        max_requests=settings.rate_limit_auth_requests,
        window_seconds=settings.rate_limit_auth_window_seconds,
    )
