import pytest

from app.deps import get_router
from app.main import app
from app.providers.errors import FatalProviderError
from app.routing.router import Router

from test_chat_fallback import FakeAdapter, make_response

pytestmark = pytest.mark.asyncio


async def test_stats_with_no_requests_returns_zeroed_summary(client):
    resp = await client.get("/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_requests"] == 0
    assert body["success_rate"] == 0.0
    assert body["fallback_rate"] == 0.0
    assert body["by_provider"] == {}


async def test_stats_reflects_successful_and_failed_requests(client, seeded_api_key_pair):
    raw_key, _ = seeded_api_key_pair
    headers = {"Authorization": f"Bearer {raw_key}"}
    payload = {"model": "fast-cheap", "messages": [{"role": "user", "content": "hi"}]}

    # Request 1: groq succeeds directly (no fallback).
    app.dependency_overrides[get_router] = lambda: Router(
        adapters={
            "groq": FakeAdapter("groq", [make_response("ok")]),
            "openai": FakeAdapter("openai", [make_response("unused")]),
        }
    )
    resp1 = await client.post("/v1/chat", headers=headers, json=payload)
    assert resp1.status_code == 200

    # Request 2: groq fails, openai succeeds (fallback).
    app.dependency_overrides[get_router] = lambda: Router(
        adapters={
            "groq": FakeAdapter("groq", [FatalProviderError("down")]),
            "openai": FakeAdapter("openai", [make_response("fallback ok")]),
        }
    )
    resp2 = await client.post("/v1/chat", headers=headers, json=payload)
    assert resp2.status_code == 200

    # Request 3: both fail.
    app.dependency_overrides[get_router] = lambda: Router(
        adapters={
            "groq": FakeAdapter("groq", [FatalProviderError("down")]),
            "openai": FakeAdapter("openai", [FatalProviderError("also down")]),
        }
    )
    resp3 = await client.post("/v1/chat", headers=headers, json=payload)
    assert resp3.status_code == 502

    stats_resp = await client.get("/stats")
    body = stats_resp.json()

    assert body["total_requests"] == 3
    assert body["success_rate"] == round(2 / 3, 4)
    assert body["fallback_rate"] == round(1 / 3, 4)
    assert body["avg_latency_ms"] >= 0
    assert body["total_estimated_cost_usd"] > 0

    assert body["by_provider"]["groq"]["requests"] == 1
    assert body["by_provider"]["groq"]["success_rate"] == 1.0
    assert body["by_provider"]["openai"]["requests"] == 1
    assert body["by_provider"]["openai"]["success_rate"] == 1.0


async def test_stats_excludes_rate_limited_requests_from_by_provider(client, seeded_api_key_pair, test_engine):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.deps import get_rate_limiter
    from app.ratelimit.limiter import RateLimiter

    raw_key, key_id = seeded_api_key_pair

    session_factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    async with session_factory() as session:
        await session.execute(text("UPDATE api_keys SET rate_limit_per_min = 1 WHERE id = :id"), {"id": key_id})
        await session.commit()

    app.dependency_overrides[get_router] = lambda: Router(
        adapters={
            "groq": FakeAdapter("groq", [make_response("ok")] * 5),
            "openai": FakeAdapter("openai", [make_response("ok")] * 5),
        }
    )

    import fakeredis.aioredis

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_rate_limiter] = lambda: RateLimiter(redis_client=fake_redis)

    payload = {"model": "fast-cheap", "messages": [{"role": "user", "content": "hi"}]}
    headers = {"Authorization": f"Bearer {raw_key}"}

    await client.post("/v1/chat", headers=headers, json=payload)
    second = await client.post("/v1/chat", headers=headers, json=payload)
    assert second.status_code == 429

    body = (await client.get("/stats")).json()
    assert body["total_requests"] == 2
    assert body["success_rate"] == 0.5
    # The rate_limited row has no provider_used, so it shouldn't appear in by_provider.
    assert sum(p["requests"] for p in body["by_provider"].values()) == 1
