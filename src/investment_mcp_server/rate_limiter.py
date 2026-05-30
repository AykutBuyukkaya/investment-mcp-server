"""Async token-bucket rate limiter for upstream HTTP client throttling."""

from __future__ import annotations

import asyncio
import math
import time


class RateLimiter:
    """Async token-bucket rate limiter.

    Tokens refill at ``refill_rate`` tokens per second up to ``capacity``.
    Each :meth:`acquire` call consumes one token, waiting if none are available.

    Usage::

        limiter = RateLimiter.from_rps(5.0)   # 5 req/s, burst 10
        await limiter.acquire()                 # blocks if bucket is empty
        response = await client.get(url)
    """

    def __init__(self, *, capacity: float, refill_rate: float) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be > 0")
        if refill_rate <= 0:
            raise ValueError("refill_rate must be > 0")
        self._capacity = float(capacity)
        self._refill_rate = float(refill_rate)
        self._tokens = float(capacity)
        self._last_refill: float = time.monotonic()
        self._lock: asyncio.Lock | None = None

    @classmethod
    def from_rps(cls, rps: float) -> "RateLimiter":
        """Create a limiter at ``rps`` requests/s with 2x burst headroom."""
        capacity = max(1.0, math.ceil(rps * 2))
        return cls(capacity=capacity, refill_rate=rps)

    def _get_lock(self) -> asyncio.Lock:
        # Lazily create the lock so the object can be constructed outside an
        # event loop (e.g. at module import time or in tests).
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def acquire(self, tokens: float = 1.0) -> None:
        """Block until ``tokens`` tokens are available, then consume them."""
        lock = self._get_lock()
        while True:
            async with lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return
                wait = (tokens - self._tokens) / self._refill_rate
            await asyncio.sleep(wait)

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_rate)
        self._last_refill = now
