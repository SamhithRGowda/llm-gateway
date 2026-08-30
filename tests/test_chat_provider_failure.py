import pytest

from app.deps import get_router
from app.main import app
from app.providers.errors import FatalProviderError
from app.routing.router import Router

from test_chat_fallback import FakeAdapter

pytestmark = pytest.mark.asyncio


async def test_chat_returns_502_when_all_providers_fail(client, seeded_api_key_pair, fetch_request_logs):
    raw_key, _ = seeded_api_key_pair

    groq = FakeAdapter("groq", [FatalProviderError("groq is down")])
    openai = FakeAdapter("openai", [FatalProviderError("openai is down too")])
    app.dependency_overrides[get_router] = lambda: Router(adapters={"groq": groq, "openai": openai})

    resp = await client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"model": "fast-cheap", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert resp.status_code == 502
    body = resp.json()
    assert body["error"] == "all_providers_failed"
    attempts = body["attempts"]
    assert [a["provider"] for a in attempts] == ["groq", "openai"]
    assert all("error_type" in a and "message" in a for a in attempts)
    # No raw provider response bodies / secrets leaked -- just type + message.
    assert all(set(a.keys()) == {"provider", "error_type", "message"} for a in attempts)

    rows = await fetch_request_logs()
    assert len(rows) == 1
    assert rows[0]["status"] == "all_failed"
    assert rows[0]["provider_used"] is None
