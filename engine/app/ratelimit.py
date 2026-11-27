"""In-memory token bucket per token/IP. CLEAN-ROOM DESIGN (SPEC §2.8): 120 req/min general, 600 req/min ingest."""
from __future__ import annotations

import math
import threading
import time
from typing import Any


class TokenBucket:
    __slots__ = ("capacity", "refill", "tokens", "last")

    def __init__(self, rate_per_min: int) -> None:
        self.capacity = float(max(1, int(rate_per_min)))
        self.refill = self.capacity / 60.0
        self.tokens = self.capacity
        self.last = time.monotonic()

    def allow(self) -> tuple[bool, int]:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.refill)
        self.last = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True, 0
        return False, max(1, int(math.ceil((1.0 - self.tokens) / self.refill)))


class RateLimiter:
    def __init__(self, rate_per_min: int) -> None:
        self.rate_per_min = int(rate_per_min)
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, int]:
        with self._lock:
            if len(self._buckets) > 10000:
                self._buckets.clear()
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = self._buckets[key] = TokenBucket(self.rate_per_min)
            return bucket.allow()

    def reset(self, key: Any = None) -> None:
        with self._lock:
            if key is None:
                self._buckets.clear()
            else:
                self._buckets.pop(key, None)
