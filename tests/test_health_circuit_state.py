import pytest

from app.deps import get_router
from app.main import app
from app.providers.errors import FatalProviderError
from app.reliability.circuit_breaker import CircuitBreaker
from app.routing.router import Router

from test_chat_fallback import FakeAdapter, make_response

pytestmark = pytest.mark.asyncio


async def test_health_reports_closed_state_by_default(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["providers"]["openai"]["circuit_state"] == "closed"
    assert body["providers"]["groq"]["circuit_state"] == "closed"


async def test_health_reflects_open_circuit_for_a_failing_provider(client):
    groq_breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=999)
    openai_breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=999)
    router = Router(
        adapters={
            "groq": FakeAdapter("groq", [FatalProviderError("down")]),
            "openai": FakeAdapter("openai", [make_response("ok")]),
        },
        circuit_breakers={"groq": groq_breaker, "openai": openai_breaker},
    )
    app.dependency_overrides[get_router] = lambda: router

    # Trip groq's breaker via a real routed request.
    from app.providers.base import NormalizedRequest

    await router.route("fast-cheap", NormalizedRequest(messages=[{"role": "user", "content": "hi"}]))

    resp = await client.get("/health")
    body = resp.json()
    assert body["providers"]["groq"]["circuit_state"] == "open"
    assert body["providers"]["openai"]["circuit_state"] == "closed"
