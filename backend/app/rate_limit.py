from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from fastapi import HTTPException


class SlidingWindowLimiter:
    """Small process-local guard for expensive/auth endpoints.

    This is deliberately dependency-free. A shared Redis-backed limiter can replace it
    later for multi-instance deployments without changing route behavior.
    """

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str) -> None:
        now = monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                raise HTTPException(status_code=429, detail="Too many attempts. Please try again shortly.")
            events.append(now)


auth_limiter = SlidingWindowLimiter(limit=12, window_seconds=300)
