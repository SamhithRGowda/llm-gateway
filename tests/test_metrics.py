import pytest

from app.deps import get_router
from app.main import app
from app.routing.router import Router

from test_chat_fallback import FakeAdapter, make_response

pytestmark = pytest.mark.asyncio


async def test_metrics_endpoint_returns_prometheus_exposition_format(client):
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    # Content-Type should carry the Prometheus exposition version param.
    assert "version=" in resp.headers["content-type"]


async def test_metrics_reflects_a_successful_chat_request(client, seeded_api_key_pair):
    raw_key, _ = seeded_api_key_pair

    groq = FakeAdapter("groq", [make_response("hi")])
    openai = FakeAdapter("openai", [make_response("unused")])
    app.dependency_overrides[get_router] = lambda: Router(adapters={"groq": groq, "openai": openai})

    await client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"model": "fast-cheap", "messages": [{"role": "user", "content": "hi"}]},
    )

    resp = await client.get("/metrics")
    body = resp.text

    assert 'gateway_requests_total{model_alias="fast-cheap",provider="groq",status="success"}' in body
    assert "gateway_request_latency_seconds_count" in body
    assert 'gateway_tokens_total{direction="input",provider="groq"}' in body
    assert "gateway_estimated_cost_usd_total" in body


async def test_metrics_reflects_fallback_event(client, seeded_api_key_pair):
    from app.providers.errors import FatalProviderError

    raw_key, _ = seeded_api_key_pair

    groq = FakeAdapter("groq", [FatalProviderError("down")])
    openai = FakeAdapter("openai", [make_response("from openai")])
    app.dependency_overrides[get_router] = lambda: Router(adapters={"groq": groq, "openai": openai})

    await client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"model": "fast-cheap", "messages": [{"role": "user", "content": "hi"}]},
    )

    resp = await client.get("/metrics")
    body = resp.text
    assert 'gateway_fallback_events_total{from_provider="groq",to_provider="openai"}' in body


async def test_metrics_reflects_rate_limit_exceeded(client, seeded_api_key_pair, test_engine):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.deps import get_rate_limiter
    from app.ratelimit.limiter import RateLimiter

    raw_key, key_id = seeded_api_key_pair

    session_factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    async with session_factory() as session:
        await session.execute(text("UPDATE api_keys SET rate_limit_per_min = 1 WHERE id = :id"), {"id": key_id})
        await session.commit()

    groq = FakeAdapter("groq", [make_response("ok")] * 5)
    openai = FakeAdapter("openai", [make_response("ok")] * 5)
    app.dependency_overrides[get_router] = lambda: Router(adapters={"groq": groq, "openai": openai})

    import fakeredis.aioredis

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_rate_limiter] = lambda: RateLimiter(redis_client=fake_redis)

    payload = {"model": "fast-cheap", "messages": [{"role": "user", "content": "hi"}]}
    headers = {"Authorization": f"Bearer {raw_key}"}

    await client.post("/v1/chat", headers=headers, json=payload)
    second = await client.post("/v1/chat", headers=headers, json=payload)
    assert second.status_code == 429

    resp = await client.get("/metrics")
    body = resp.text
    assert "gateway_rate_limit_exceeded_total" in body
    assert 'api_key_label="chat-test-client"' in body
