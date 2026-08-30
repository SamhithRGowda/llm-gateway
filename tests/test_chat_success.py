import uuid

import pytest

from app.deps import get_router
from app.main import app
from app.routing.router import Router

from test_chat_fallback import FakeAdapter, make_response

pytestmark = pytest.mark.asyncio


async def test_chat_without_api_key_returns_401(client):
    resp = await client.post(
        "/v1/chat",
        json={"model": "fast-cheap", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 401


async def test_chat_success_returns_normalized_response(client, seeded_api_key_pair, fetch_request_logs):
    raw_key, key_id = seeded_api_key_pair

    groq = FakeAdapter("groq", [make_response("Hello from groq")])
    openai = FakeAdapter("openai", [make_response("unused")])
    app.dependency_overrides[get_router] = lambda: Router(adapters={"groq": groq, "openai": openai})

    resp = await client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"model": "fast-cheap", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "groq"
    assert body["model_alias"] == "fast-cheap"
    assert body["content"] == "Hello from groq"
    assert body["fallback_occurred"] is False
    assert body["usage"]["input_tokens"] == 1
    assert body["usage"]["output_tokens"] == 1
    assert body["usage"]["total_tokens"] == 2
    assert isinstance(body["usage"]["estimated_cost_usd"], float)
    assert isinstance(body["latency_ms"], int)
    assert body["id"].startswith("req_")

    rows = await fetch_request_logs()
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "success"
    assert row["provider_used"] == "groq"
    assert row["fallback_occurred"] in (0, False)
    # SQLAlchemy's Uuid type stores as undashed hex on SQLite; compare as UUIDs.
    assert uuid.UUID(row["api_key_id"]) == uuid.UUID(key_id)


async def test_chat_fallback_marks_fallback_occurred_and_logs_status(client, seeded_api_key_pair, fetch_request_logs):
    raw_key, _ = seeded_api_key_pair

    from app.providers.errors import FatalProviderError

    groq = FakeAdapter("groq", [FatalProviderError("groq down")])
    openai = FakeAdapter("openai", [make_response("from openai")])
    app.dependency_overrides[get_router] = lambda: Router(adapters={"groq": groq, "openai": openai})

    resp = await client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"model": "fast-cheap", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "openai"
    assert body["fallback_occurred"] is True

    rows = await fetch_request_logs()
    assert rows[0]["status"] == "fallback_success"
