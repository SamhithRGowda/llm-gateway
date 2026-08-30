"""Redis-backed token bucket rate limiter, per PLAN.md Section 9.

Algorithm: token bucket, continuously refilled based on elapsed time,
implemented as a single atomic Lua script (EVAL) so concurrent requests for
the same key can't race past the limit. State (tokens remaining, last refill
timestamp) is stored in a Redis hash at `ratelimit:{api_key_id}`, with a TTL
set slightly above the refill window so idle keys clean themselves up.
"""
import time
from dataclasses import dataclass

import redis.asyncio as redis

from app.config import settings

# KEYS[1] = bucket key
# ARGV[1] = capacity (max tokens = limit_per_min)
# ARGV[2] = refill_rate_per_sec (capacity / 60)
# ARGV[3] = now (unix timestamp, seconds, float)
# ARGV[4] = ttl (seconds)
# Returns {allowed (0/1), tokens_remaining (string, for retry-after math)}
_TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])

local bucket = redis.call("HMGET", key, "tokens", "last_refill")
local tokens = tonumber(bucket[1])
local last_refill = tonumber(bucket[2])

if tokens == nil then
    tokens = capacity
    last_refill = now
end

local elapsed = now - last_refill
if elapsed < 0 then elapsed = 0 end
tokens = math.min(capacity, tokens + elapsed * refill_rate)

local allowed = 0
if tokens >= 1 then
    tokens = tokens - 1
    allowed = 1
end

redis.call("HMSET", key, "tokens", tostring(tokens), "last_refill", tostring(now))
redis.call("EXPIRE", key, ttl)

return {allowed, tostring(tokens)}
"""


@dataclass
class RateLimitResult:
    allowed: bool
    retry_after_seconds: float


class RateLimiter:
    def __init__(self, redis_client: "redis.Redis | None" = None):
        self._redis = redis_client if redis_client is not None else redis.from_url(
            settings.redis_url, decode_responses=True
        )
        self._script = self._redis.register_script(_TOKEN_BUCKET_LUA)

    async def check(self, api_key_id: str, limit_per_min: int) -> RateLimitResult:
        """Attempt to consume one token from the bucket for `api_key_id`.

        `limit_per_min` is the bucket capacity and refill target (tokens/min).
        """
        capacity = max(limit_per_min, 1)
        refill_rate_per_sec = capacity / 60.0
        now = time.time()
        ttl_seconds = int(60 / refill_rate_per_sec) + 10  # window + small buffer

        key = f"ratelimit:{api_key_id}"
        raw_allowed, raw_tokens = await self._script(
            keys=[key], args=[capacity, refill_rate_per_sec, now, ttl_seconds]
        )

        allowed = bool(int(raw_allowed))
        tokens_remaining = float(raw_tokens)

        if allowed:
            retry_after = 0.0
        else:
            retry_after = round((1 - tokens_remaining) / refill_rate_per_sec, 2)

        return RateLimitResult(allowed=allowed, retry_after_seconds=max(retry_after, 0.0))
