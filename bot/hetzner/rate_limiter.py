import asyncio
import time
from dataclasses import dataclass, field

from bot.config import get_settings


@dataclass
class TokenBucket:
    capacity: int
    refill_rate: float
    tokens: float = field(init=False)
    last_refill: float = field(init=False)

    def __post_init__(self):
        self.tokens = float(self.capacity)
        self.last_refill = time.monotonic()

    def consume(self, tokens: int = 1) -> float:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return 0.0

        deficit = tokens - self.tokens
        wait_time = deficit / self.refill_rate
        return wait_time


class HetznerRateLimiter:
    def __init__(self):
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = asyncio.Lock()
        self._settings = get_settings()

    def _get_bucket(self, token: str) -> TokenBucket:
        if token not in self._buckets:
            self._buckets[token] = TokenBucket(
                capacity=int(self._settings.hetzner_max_requests_per_second * 2),
                refill_rate=self._settings.hetzner_max_requests_per_second,
            )
        return self._buckets[token]

    async def acquire(self, token: str) -> None:
        async with self._lock:
            bucket = self._get_bucket(token)
            wait_time = bucket.consume(1)

        if wait_time > 0:
            await asyncio.sleep(wait_time)

    def update_from_headers(self, token: str, headers: dict) -> None:
        try:
            remaining = int(headers.get("RateLimit-Remaining", "0"))
            limit = int(headers.get("RateLimit-Limit", "0"))
            reset = int(headers.get("RateLimit-Reset", "0"))

            if limit > 0:
                async with self._lock:
                    bucket = self._get_bucket(token)
                    bucket.capacity = limit
                    bucket.refill_rate = limit / max(reset, 1)
                    bucket.tokens = remaining
                    bucket.last_refill = time.monotonic()
        except (ValueError, KeyError):
            pass


rate_limiter = HetznerRateLimiter()
