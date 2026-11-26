import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.core.config import get_settings

# In-process sliding window. Fine for a single API process; swap for Redis before scaling out.
_hits: dict[str, deque] = defaultdict(deque)


def reset() -> None:
    _hits.clear()


def rate_limit(name: str, limit: int, window_s: int = 60):
    def dep(request: Request) -> None:
        if not get_settings().rate_limit_enabled:
            return
        ip = request.client.host if request.client else "unknown"
        q = _hits[f"{name}:{ip}"]
        now = time.monotonic()
        while q and q[0] <= now - window_s:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(429, "rate_limited", headers={"Retry-After": str(window_s)})
        q.append(now)

    return dep
