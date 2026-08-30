"""Rate limiting tests, per PLAN.md Phase 5.

Uses fakeredis (with lupa for Lua scripting support) instead of a real Redis
server -- no external services are touched.
"""
import asyncio

import fakeredis.aioredis
import pytest

from app.deps import get_rate_limiter, get_router
from app.main import app
from app.ratelimit.limiter import RateLimiter
from app.routing.router import Router

from test_chat_fallback import FakeAdapter, make_response

pytestmark = pytest.mark.asyncio


def make_fake_redis() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


# --- Unit tests: RateLimiter against fakeredis directly ---------------------


async def test_first_request_within_limit_is_allowed():
    limiter = RateLimiter(redis_client=make_fake_redis())
    result = await limiter.check(api_key_id="key-1", limit_per_min=60)
    assert result.allowed is True
    assert result.retry_after_seconds == 0.0


async def test_requests_beyond_limit_are_rejected_with_retry_after():
    limiter = RateLimiter(redis_client=make_fake_redis())
    # capacity of 2: first two calls succeed, third is rejected.
    r1 = await limiter.check(api_key_id="key-2", limit_per_min=2)
    r2 = await limiter.check(api_key_id="key-2", limit_per_min=2)
    r3 = await limiter.check(api_key_id="key-2", limit_per_min=2)

    assert r1.allowed is True
    assert r2.allowed is True
    assert r3.allowed is False
    assert r3.retry_after_seconds > 0


async def test_different_api_keys_have_independent_buckets():
    fake_redis = make_fake_redis()
    limiter = RateLimiter(redis_client=fake_redis)

    # Exhaust key-a's single-token bucket.
    await limiter.check(api_key_id="key-a", limit_per_min=1)
    exhausted = await limiter.check(api_key_id="key-a", limit_per_min=1)
    assert exhausted.allowed is False

    # key-b is untouched.
    fresh = await limiter.check(api_key_id="key-b", limit_per_min=1)
    assert fresh.allowed is True


async def test_bucket_refills_over_time():
    limiter = RateLimiter(redis_client=make_fake_redis())
    # capacity 60/min => refill rate 1 token/sec.
    await limiter.check(api_key_id="key-refill", limit_per_min=60)
    for _ in range(59):
        await limiter.check(api_key_id="key-refill", limit_per_min=60)

    # Bucket should now be exhausted.
    exhausted = await limiter.check(api_key_id="key-refill", limit_per_min=60)
    assert exhausted.allowed is False

    await asyncio.sleep(1.1)  # allow >=1 token to refill

    refilled = await limiter.check(api_key_id="key-refill", limit_per_min=60)
    assert refilled.allowed is True


# --- Integration tests: /v1/chat returns 429 when the limit is exceeded ----


async def test_chat_endpoint_returns_429_when_rate_limit_exceeded(
    client, seeded_api_key_pair, fetch_request_logs, test_engine
):
    """Also exercises the per-key rate_limit_per_min override from
    PLAN.md Section 9, by setting it to 1 directly on the seeded key."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    raw_key, key_id = seeded_api_key_pair

    session_factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    async with session_factory() as session:
        await session.execute(
            text("UPDATE api_keys SET rate_limit_per_min = 1 WHERE id = :id"), {"id": key_id}
        )
        await session.commit()

    groq = FakeAdapter("groq", [make_response("ok")] * 5)
    openai = FakeAdapter("openai", [make_response("ok")] * 5)
    app.dependency_overrides[get_router] = lambda: Router(adapters={"groq": groq, "openai": openai})

    # Create the fake Redis client once, outside the lambda -- otherwise each
    # dependency resolution would get a fresh, empty client and the bucket
    # would never persist across requests.
    test_fake_redis = make_fake_redis()
    app.dependency_overrides[get_rate_limiter] = lambda: RateLimiter(redis_client=test_fake_redis)

    payload = {"model": "fast-cheap", "messages": [{"role": "user", "content": "hi"}]}
    headers = {"Authorization": f"Bearer {raw_key}"}

    first = await client.post("/v1/chat", headers=headers, json=payload)
    assert first.status_code == 200

    second = await client.post("/v1/chat", headers=headers, json=payload)
    assert second.status_code == 429
    body = second.json()
    assert body["error"] == "rate_limit_exceeded"
    assert body["retry_after_seconds"] > 0
    assert "Retry-After" in second.headers

    rows = await fetch_request_logs()
    assert len(rows) == 2
    assert rows[0]["status"] == "success"
    assert rows[1]["status"] == "rate_limited"
    assert rows[1]["provider_used"] is None
    assert rows[1]["latency_ms"] == 0
