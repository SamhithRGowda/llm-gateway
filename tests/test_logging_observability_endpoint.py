import json
import logging

import pytest

from app.deps import get_router
from app.main import app
from app.observability.logging_config import log_chat_request
from app.routing.router import Router

from test_chat_fallback import FakeAdapter, make_response

pytestmark = pytest.mark.asyncio


async def test_chat_endpoint_emits_a_log_line_per_request(client, seeded_api_key_pair, caplog):
    raw_key, _ = seeded_api_key_pair

    groq = FakeAdapter("groq", [make_response("hi")])
    openai = FakeAdapter("openai", [make_response("unused")])
    app.dependency_overrides[get_router] = lambda: Router(adapters={"groq": groq, "openai": openai})

    with caplog.at_level(logging.INFO, logger="llm_gateway.requests"):
        resp = await client.post(
            "/v1/chat",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={"model": "fast-cheap", "messages": [{"role": "user", "content": "secret content"}]},
        )

    assert resp.status_code == 200
    matching = [r for r in caplog.records if r.name == "llm_gateway.requests"]
    assert len(matching) == 1
    fields = matching[0].fields
    assert fields["status"] == "success"
    assert fields["provider_used"] == "groq"
    assert fields["model_alias"] == "fast-cheap"
    assert isinstance(fields["latency_ms"], int)
    assert fields["fallback_occurred"] is False
    # Message content must never be logged.
    assert "secret content" not in json.dumps(fields)
