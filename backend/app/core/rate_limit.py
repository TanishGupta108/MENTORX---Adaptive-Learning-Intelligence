"""In-memory sliding-window rate limiter (FR-AUTH-07).

Good enough for a single backend instance. If the API is ever scaled to several
instances, move this to a shared store (e.g. Redis) so limits apply across them.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, now: float | None = None) -> bool:
        """Record an attempt. Returns False if the key is over its limit (attempt rejected)."""
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True

    def retry_after(self, key: str, now: float | None = None) -> int:
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits.get(key)
            if not q:
                return 0
            return max(1, int(q[0] + self.window - now) + 1)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
