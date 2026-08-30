import pytest

from app.deps import get_router
from app.main import app
from app.routing.router import Router

from test_chat_fallback import FakeAdapter, make_response

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _override_router_with_working_adapters():
    """Malformed-request cases should fail before ever reaching the router;
    this override just guarantees a test failure would be obviously
    attributable to validation, not to a missing provider."""
    groq = FakeAdapter("groq", [make_response("should not be reached")])
    openai = FakeAdapter("openai", [make_response("should not be reached")])
    app.dependency_overrides[get_router] = lambda: Router(adapters={"groq": groq, "openai": openai})
    yield
    app.dependency_overrides.pop(get_router, None)


async def test_missing_messages_returns_400(client, seeded_api_key_pair):
    raw_key, _ = seeded_api_key_pair
    resp = await client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"model": "fast-cheap"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_request"


async def test_empty_messages_list_returns_400(client, seeded_api_key_pair):
    raw_key, _ = seeded_api_key_pair
    resp = await client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"model": "fast-cheap", "messages": []},
    )
    assert resp.status_code == 400


async def test_invalid_role_returns_400(client, seeded_api_key_pair):
    raw_key, _ = seeded_api_key_pair
    resp = await client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"model": "fast-cheap", "messages": [{"role": "narrator", "content": "hi"}]},
    )
    assert resp.status_code == 400


async def test_empty_content_returns_400(client, seeded_api_key_pair):
    raw_key, _ = seeded_api_key_pair
    resp = await client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"model": "fast-cheap", "messages": [{"role": "user", "content": ""}]},
    )
    assert resp.status_code == 400


async def test_unknown_model_alias_returns_400(client, seeded_api_key_pair):
    raw_key, _ = seeded_api_key_pair
    resp = await client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"model": "does-not-exist", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_request"


async def test_missing_model_returns_400(client, seeded_api_key_pair):
    raw_key, _ = seeded_api_key_pair
    resp = await client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 400
