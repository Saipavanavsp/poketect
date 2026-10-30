"""Request guards: an optional admin token for edits and a per-IP rate limit for the expensive endpoints."""
import hmac
import threading
import time
from collections import defaultdict, deque

from fastapi import Header, HTTPException, Request

from . import config


def require_admin(authorization: str | None = Header(None)):
    """Edits are open while ADMIN_TOKEN is unset (local use); once set, they need the matching bearer token."""
    if not config.ADMIN_TOKEN:
        return
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token.encode(), config.ADMIN_TOKEN.encode()):
        raise HTTPException(401, "Editing the trainer needs the admin token.", headers={"WWW-Authenticate": "Bearer"})


class RateLimiter:
    """Sliding one-minute window per client IP, in memory (enough for a single API process)."""

    def __init__(self, name: str, setting: str):
        self.name, self.setting = name, setting
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def __call__(self, request: Request):
        limit = getattr(config, self.setting)
        if limit <= 0:
            return
        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with self.lock:
            hits = self.hits[ip]
            while hits and now - hits[0] > 60:
                hits.popleft()
            if len(hits) >= limit:
                retry = int(60 - (now - hits[0])) + 1
                raise HTTPException(429, f"Too many {self.name} requests - try again in {retry} s.",
                                    headers={"Retry-After": str(retry)})
            hits.append(now)
            if len(self.hits) > 10_000:  # drop idle clients so memory stays bounded
                for key in [k for k, v in self.hits.items() if not v or now - v[-1] > 60]:
                    del self.hits[key]


identify_limit = RateLimiter("identify", "RATE_LIMIT_IDENTIFY")
chat_limit = RateLimiter("chat", "RATE_LIMIT_CHAT")
